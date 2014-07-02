from django.views import generic
from django.views.generic.base import TemplateView
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.core.mail import send_mail
from profiles.models import ContributorProfile
#from allauth.account.views import RedirectAuthenticatedUserMixin
from django.shortcuts import redirect

class AccountInactiveView(TemplateView):
    #redirect_field_name = 'profile'
    template_name = 'account/account_inactive.html'
    
    redirect_field_name = "profile"
    
    def get_redirect_url(self):
        return self.redirect_field_name
    
    def get(self, request, *args, **kwargs):
        '''
        Overriding TemplateView.get() in order to
        prevent active user from seeing inactive page
        '''
        # Redirect to Profile if user is active
        if  self.request.user.is_active:
            return redirect(self.get_redirect_url())
        # Process normally if User is not activated yet
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

class PendingUsersView(generic.ListView):
    template_name = 'custom_auth/pending_users.html'
    context_object_name = 'pending_profiles'

    def get_queryset(self):
        return ContributorProfile.objects.filter(
            user__is_active__exact=False).filter(
            user__emailaddress__verified__exact=True)


def which_action(request, profile_id):
    if request.user.is_staff:
        profile = get_object_or_404(ContributorProfile, pk=profile_id)
        if 'approve_contrib' in request.POST:
            #the pk for group can_contribCI is 1
            approve(request, profile, 1)
        elif 'approve_base' in request.POST:
            #the pk for group can_useCI is 2
            approve(request,profile, 2)
        elif 'reject' in request.POST:
            reject(request, profile)
        elif 'ignore' in request.POST:
            ignore(request, profile)    
    return HttpResponseRedirect(reverse('pending_users'))

def approve(request, profile, group):
    """
    this method will set profile.user.is_active = True, save the user,
    and send an email to notify the user
    """   
    profile.user.is_active = True
    profile.user.groups.add(group)
    profile.user.save()
    
    #this doesn't work right yet
    send_mail('account_approved_subject.txt', 'account.approved_message.txt', 'from@example.com',
        [profile.user.email], fail_silently=False)
        
def reject(request, profile):
    """
    this method will send an email to notify the user, then delete the user and profile
    """
    for emailaddress in profile.user.emailaddress_set.all():
        emailaddress.delete()
    profile.user.delete()
    profile.delete()
    #this doesn't work right yet
    send_mail('account_approved_subject.txt', 'account.approved_message.txt', 'from@example.com',
        [profile.user.email], fail_silently=False)

def ignore(request, profile):
    """
    this method will delete the user and profile without notifying the user
    """
    for emailaddress in profile.user.emailaddress_set.all():
        emailaddress.delete()
    profile.user.delete()
    profile.delete()
    
    
