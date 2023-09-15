from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json

try:
    from email.mime.base import MIMEBase
except ImportError as e:
    from email import MIMEBase

__POSTMARK_URL__ = "https://api.postmarkapp.com/"


class PMJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "_proxy____unicode_cast"):
            return unicode(o)
        return super(PMJSONEncoder, self).default(o)


class PMMail(object):
    """
    The Postmark Mail object.
    """

    def __init__(self, **kwargs):
        """
        Keyword arguments are:
        api_key:        Your Postmark server API key
        sender:         Who the email is coming from, in either
                        "name@email.com" or "First Last <name@email.com>" format
        to:             Who to send the email to, in either
                        "name@email.com" or "First Last <name@email.com>" format
                        Can be multiple values separated by commas (limit 20)
        cc:             Who to copy the email to, in either
                        "name@email.com" or "First Last <name@email.com>" format
                        Can be multiple values separated by commas (limit 20)
        bcc:            Who to blind copy the email to, in either
                        "name@email.com" or "First Last <name@email.com>" format
                        Can be multiple values separated by commas (limit 20)
        subject:        Subject of the email, ignored if using Postmark templates
        html_body:      Email message in HTML
        text_body:      Email message in plain text
        track_opens:    Whether to track if emails were opened or not
        """
        # initialize properties
        self.api_key = None
        self.sender = None
        self.to = None
        self.cc = None
        self.bcc = None
        self.subject = None
        self.html_body = None
        self.message_id = None
        self.text_body = None
        self.track_opens = False
        self.attachments = []
        self.reply_to = None

        acceptable_keys = (
            "api_key",
            "sender",
            "to",
            "cc",
            "bcc",
            "subject",
            "html_body",
            "text_body",
            "track_opens",
            "attachments",
            "reply_to",
        )

        for key in kwargs:
            if key in acceptable_keys:
                setattr(self, key, kwargs[key])

    def to_json_message(self):
        json_message = {
            "From": self.sender,
            "To": self.to,
            "Subject": self.subject,
        }
        if self.cc:
            json_message["Cc"] = self.cc
        if self.bcc:
            json_message["Bcc"] = self.bcc
        if self.reply_to:
            json_message["ReplyTo"] = self.reply_to
        if self.html_body:
            json_message["HtmlBody"] = self.html_body
        if self.text_body:
            json_message["TextBody"] = self.text_body
        if self.track_opens:
            json_message["TrackOpens"] = True
        if len(self.attachments) > 0:
            attachments = []
            for attachment in self.attachments:
                if isinstance(attachment, tuple):
                    file_item = {
                        "Name": attachment[0],
                        "Content": attachment[1],
                        "ContentType": attachment[2],
                    }
                    # If need add Content-ID header:
                    if len(attachment) >= 4 and attachment[3]:
                        file_item["ContentID"] = attachment[3]
                elif isinstance(attachment, MIMEBase):
                    file_item = {
                        "Name": attachment.get_filename(),
                        "Content": attachment.get_payload(),
                        "ContentType": attachment.get_content_type(),
                    }
                    content_id = attachment.get("Content-ID")
                    if content_id:
                        # Because postmarkapp api required clear value. Not enclosed in angle brackets:
                        if content_id.startswith("<") and content_id.endswith(">"):
                            content_id = content_id[1:-1]
                        # Postmarkapp will mark attachment as "inline" only if "ContentID" field starts with "cid":
                        if (attachment.get("Content-Disposition") or "").startswith(
                            "inline"
                        ):
                            content_id = "cid:%s" % content_id
                        file_item["ContentID"] = content_id
                else:
                    continue
                attachments.append(file_item)
            json_message["Attachments"] = attachments

        return json_message

    def send(self, test=None):
        """
        Send the email through the Postmark system.
        Pass test=True to just print out the resulting
        JSON message being sent to Postmark
        """
        json_message = self.to_json_message()

        endpoint_url = __POSTMARK_URL__ + "email"

        # Set up the url Request
        req = Request(
            endpoint_url,
            json.dumps(json_message, cls=PMJSONEncoder).encode("utf8"),
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": self.api_key,
            },
        )

        # Attempt send
        try:
            # print 'sending request to postmark: %s' % json_message
            result = urlopen(req)
            jsontxt = result.read().decode("utf8")
            result.close()
            if result.code == 200:
                self.message_id = json.loads(jsontxt).get("MessageID", None)
                return self.message_id
            else:
                raise PMMailSendException(
                    "Return code %d: %s" % (result.code, result.msg)
                )

        except HTTPError as err:
            if err.code == 401:
                raise PMMailUnauthorizedException(
                    "Sending Unauthorized - incorrect API key.", err
                )
            elif err.code == 422:
                try:
                    jsontxt = err.read().decode("utf8")
                    jsonobj = json.loads(jsontxt)
                    desc = jsonobj["Message"]
                    error_code = jsonobj["ErrorCode"]
                except KeyError:
                    raise PMMailUnprocessableEntityException(
                        "Unprocessable Entity: Description not given"
                    )

                if error_code == 406:
                    raise PMMailInactiveRecipientException(
                        "You tried to send email to a recipient that has been marked as inactive."
                    )

                raise PMMailUnprocessableEntityException(
                    "Unprocessable Entity: %s" % desc
                )
            elif err.code == 500:
                raise PMMailServerErrorException(
                    "Internal server error at Postmark. Admins have been alerted.", err
                )
        except URLError as err:
            if hasattr(err, "reason"):
                raise PMMailURLException(
                    'URLError: Failed to reach the server: %s (See "inner_exception" for details)'
                    % err.reason,
                    err,
                )
            elif hasattr(err, "code"):
                raise PMMailURLException(
                    'URLError: %d: The server couldn\'t fufill the request. (See "inner_exception" for details)'
                    % err.code,
                    err,
                )
            else:
                raise PMMailURLException(
                    'URLError: The server couldn\'t fufill the request. (See "inner_exception" for details)',
                    err,
                )


class PMMailSendException(Exception):
    """
    Base Postmark send exception
    """

    def __init__(self, value, inner_exception=None):
        self.parameter = value
        self.inner_exception = inner_exception

    def __str__(self):
        return repr(self.parameter)


class PMMailUnauthorizedException(PMMailSendException):
    """
    401: Unathorized sending due to bad API key
    """

    pass


class PMMailUnprocessableEntityException(PMMailSendException):
    """
    422: Unprocessable Entity - usually an exception with either the sender
    not having a matching Sender Signature in Postmark.  Read the message
    details for further information
    """

    pass


class PMMailInactiveRecipientException(PMMailSendException):
    """
    406: You tried to send a message to a recipient that has been marked as
    inactive. If this was a batch operation, the rest of the messages were
    still sent.
    """

    pass


class PMMailServerErrorException(PMMailSendException):
    """
    500: Internal error - this is on the Postmark server side.  Errors are
    logged and recorded at Postmark.
    """

    pass


class PMMailURLException(PMMailSendException):
    """
    A URLError was caught - usually has to do with connectivity
    and the ability to reach the server.  The inner_exception will
    have the base URLError object.
    """

    pass
