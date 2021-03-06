from django import forms

from django.utils.translation import ugettext_lazy as _
from allauth.account.forms import LoginForm as BaseLoginForm
from django.contrib.auth import authenticate

from profiles.models import ContributorProfile

class SignupForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SignupForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if 'interest_in' not in field_name:
                field.widget.attrs['class'] = 'form-control'

    email = forms.EmailField(widget=forms.TextInput(attrs={'type': 'email',
                                                           'placeholder': _('E-mail address')}))
    name = forms.CharField(label=_("Name"),
                           max_length=255,
                           widget=forms.TextInput(attrs={'placeholder': _('Your name'),
                                                         'autofocus': 'autofocus'}))
    
    institution = forms.CharField(label=_("Institution"),
                                  max_length=200,
                                  widget=forms.TextInput(attrs={'placeholder': _('Institution')}))
    
    homepage = forms.URLField(label=_("Homepage"),
                              max_length=200,
                              widget=forms.URLInput(attrs={'type': 'url',
                                                           'placeholder': _('Faculty homepage')}))
    
    interest_in_devel = forms.BooleanField(label=_("I am interested in helping with CI development"),
                                           required=False,
                                           )

    interest_in_deploy = forms.BooleanField(label=_("I am interested in helping to deploy the CI"),
                                           required=False,
                                           )
    
    text_info = forms.CharField(label=_("Anything else we should know?"),
                                required=False,
                                widget=forms.Textarea())

    def signup(self, request, user):
        """
        Invoked at signup time to complete the signup of the user.
        """
        user_institution = self.cleaned_data.get('institution')
        user_homepage = self.cleaned_data.get('homepage')
        user_i_devel = self.cleaned_data.get('interest_in_devel')
        user_i_deploy = self.cleaned_data.get('interest_in_deploy')
        user_text_info = self.cleaned_data.get('text_info')
        user_profile = ContributorProfile(user=user,
                                          institution = user_institution,
                                          homepage=user_homepage,
                                          interest_in_devel=user_i_devel,
                                          interest_in_deploy=user_i_deploy,
                                          text_info=user_text_info )
        user_profile.save()


class LoginForm(BaseLoginForm):
    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
    
    def clean(self):
        if self._errors:
            return
        user = authenticate(**self.user_credentials())
        if user:
            self.user = user
        else:
            raise forms.ValidationError(_("The e-mail address and/or password you specified"
                                          " are not correct."))
        return self.cleaned_data
