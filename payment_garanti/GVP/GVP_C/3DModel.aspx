﻿<%@ Page Language="C#" AutoEventWireup="true" CodeBehind="3DModel.aspx.cs" Inherits="$safeprojectname$._DModel" %>

<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" >
<head runat="server">
    <title>3D MODEL</title>
</head>
<body>
    <form id="form1" runat="server">
    <div>
        Card Number: <asp:TextBox ID="cardnumber" runat="server" />
        <br />
        Expire Date (mm): <asp:TextBox ID="cardexpiredatemonth" runat="server" />
        <br />
        Expire Date (yy): <asp:TextBox ID="cardexpiredateyear" runat="server" />
        <br />
        CVV2: <asp:TextBox ID="cardcvv2" runat="server" />
        <br />
        <asp:Button ID="submit" runat="server" PostBackUrl="https://sanalposprov.garanti.com.tr/servlet/gt3dengine" Text="İşlemi Gönder" />
        <asp:HiddenField ID="mode" runat="server" />
        <asp:HiddenField ID="secure3dsecuritylevel" Value="3D" runat="server" />
        <asp:HiddenField ID="apiversion" runat="server" />
        <asp:HiddenField ID="terminalprovuserid" runat="server" />
        <asp:HiddenField ID="terminaluserid" runat="server" />
        <asp:HiddenField ID="terminalmerchantid" runat="server" />
        <asp:HiddenField ID="txntype" runat="server" />
        <asp:HiddenField ID="txnamount" runat="server" />
        <asp:HiddenField ID="txncurrencycode" runat="server" />
        <asp:HiddenField ID="txninstallmentcount" runat="server" />
        <asp:HiddenField ID="orderid" runat="server" />
        <asp:HiddenField ID="terminalid" runat="server" />
        <asp:HiddenField ID="successurl" runat="server" />
        <asp:HiddenField ID="errorurl" runat="server" />
        <asp:HiddenField ID="customeremailaddress" runat="server" />
        <asp:HiddenField ID="customeripaddress" runat="server" />
        <asp:HiddenField ID="secure3dhash" runat="server" />
    </div>
    </form>
</body>
</html>
