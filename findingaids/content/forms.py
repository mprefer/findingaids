from recaptcha.client import captcha

from django import forms
from django.conf import settings
from django.core.mail import send_mail
from django.utils.safestring import mark_safe

class FeedbackForm(forms.Form):
    '''Simple Feedback form with reCAPTCHA.  Expects reCAPTCHA keys to be set
    in settings as RECAPTCHA_PUBLIC_KEY and RECAPTCHA_PRIVATE_KEY.  Form
    validation includes checking the CAPTCHA response.

    Captcha challenge html should be added to the form using
    :meth:`captcha_challenge`.

    When initializing this form to do validation, you must pass in the user's
    IP address, because it is required when submitting the captcha response
    for validation.  Example::

        form = FeedbackForm(data=request.POST, remote_ip=request.META['REMOTE_ADDR'])
    '''
    name = forms.CharField(required=False)
    email = forms.EmailField(required=False)
    message = forms.CharField(widget=forms.Textarea, required=True)

    # fields that will be generated by recaptcha client  display_html
    # mapping here in order to access the data
    recaptcha_challenge_field = forms.CharField(widget=forms.HiddenInput)
    recaptcha_response_field = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, data=None, remote_ip=None, **kwargs):
        self.remote_ip  = remote_ip
        super(FeedbackForm, self).__init__(data=data, **kwargs)


    def captcha_challenge(self):
        '''Generate & display a captcha challenge.  Should be included when you
        output the form.'''
        return mark_safe(captcha.displayhtml(settings.RECAPTCHA_PUBLIC_KEY))

    def clean(self):
        '''Check the CAPTCHA response as part of form validation.'''
        cleaned_data = self.cleaned_data
        # submit the challenge data for validation
        captcha_response = captcha.submit(cleaned_data['recaptcha_challenge_field'],
            cleaned_data['recaptcha_response_field'],
            settings.RECAPTCHA_PRIVATE_KEY,
            self.remote_ip,
        )        
        if not captcha_response.is_valid:
            # incorrect solution (currently seems to be the only code recaptcha.client sets)
            if captcha_response.err_code == 'incorrect-captcha-sol':
                raise forms.ValidationError("CAPTCHA response incorrect")
            else:
                raise forms.ValidationError("Could not validate CAPTCHA response")
            
        return cleaned_data
            
    def send_email(self):
        '''Send an email based on the posted form data.
        This method should not be called unless the form has validated.

        Sends a "Site Feedback" email to feedback email address configured
        in Django settings with the message submitted on the form.  If email
        and name are specified, they will be used as the From: address in the
        email that is generated; otherwise, the email will be sent from the
        SERVER_EMAIL setting configured in Django settings.

        Returns true when the email send.  Could raise an
        :class:`smtplib.SMTPException` if something goes wrong at the SMTP
        level.
        '''
        # construct a simple text message with the data from the form
        message = '''
Name:                %(name)s
Email:               %(email)s

%(message)s
''' % self.cleaned_data
        
        # email & name are optional; if they are set, use as From: address for the email
        if self.cleaned_data['email']:
            # if name is set, use both name and email 
            if self.cleaned_data['name']:
                from_email = '"%(name)s" <%(email)s>' % self.cleaned_data
            # otherwise, use just email
            else:
                from_email = self.cleaned_data['email']
        # if no email was specified, use configured server email
        else:
            from_email = settings.SERVER_EMAIL

        # send an email with settings comparable to mail_admins or mail_managers
        return send_mail(
            settings.EMAIL_SUBJECT_PREFIX + 'Site Feedback',   # subject
            message,                                           # email text
            from_email,                                        # from address
            settings.FEEDBACK_EMAIL,                           # list of recipient emails
        )