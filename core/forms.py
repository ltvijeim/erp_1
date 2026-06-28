from django import forms

class APILoginForm(forms.Form):
    username = forms.CharField(max_length=150, required=True)
    password = forms.CharField(widget=forms.PasswordInput, required=True)

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(required=True)

class PasswordResetConfirmForm(forms.Form):
    uidb64 = forms.CharField(required=True)
    token = forms.CharField(required=True)
    new_password = forms.CharField(widget=forms.PasswordInput, required=True)