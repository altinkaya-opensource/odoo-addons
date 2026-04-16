from . import models
from . import services


def post_load():
    """Install the service-level monkeypatches once the server is ready."""
    from .services.auth_detect import patch_users_check
    from .services.execute_kw_patch import patch_execute_kw

    patch_users_check()
    patch_execute_kw()
