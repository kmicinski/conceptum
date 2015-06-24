from datetime import timedelta, datetime, date, time

from django import forms
from django.utils.translation import ugettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.validators import validate_email, ValidationError
from django.db import models, transaction

from interviews.models import get_concept_list, DummyConcept as Concept #TEMPORARY: DummyConcept
from .models import ExamResponse, FreeResponseQuestion, MultipleChoiceQuestion, \
                    MultipleChoiceOption, ResponseSet, \
                    MAX_CHOICES, REQUIRED_CHOICES
import reversion

MAX_EMAILS = 30 # I don't think this is currently checked

class MultiEmailField(forms.Field):
    """
    Field to collect email addresses as one large text input, where addresses are
    seperated by semi-colon. After processing, the data is accessed as an array
    of email strings.
    """
    def to_python(self, value):
        """
        Normalize data to a list of strings.
        """
        if not value:
            return []
        value = ''.join(value.split()) #remove whitespace
        strings = value.split(";")
        if '' in strings:
            strings.remove('') #in case there was a trailing ';'
        return strings

    def validate(self, value):
        """
        Check if value consists only of valid emails.
        """
        super(MultiEmailField, self).validate(value)
        for email in value:
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError("One or more email addresses is invalid.")


class ExamResponseChoiceField(forms.ModelMultipleChoiceField):
    """
    A custom field used in DistributeForm so that the list of pending exams (for re-sending)
    displays the respondent's email.
    """
    def label_from_instance(self, obj):
        return obj.respondent


class SelectConceptForm(forms.Form):
    """
    A form for selecting a concept
    """
    concept = forms.ModelChoiceField(queryset=get_concept_list(),
                                     to_field_name="name", )


class AddFreeResponseForm(forms.ModelForm):
    """
    Form for adding a free response questions
    """
    question = models.CharField(blank = False)
   
    class Meta:
        model = FreeResponseQuestion
        fields = ['question','image']
        widgets = {'question': forms.TextInput(attrs={'size': '60'})}
    

class AddMultipleChoiceForm(forms.ModelForm):
    """
    Form for adding a multiple choice question
    """
    class Meta:
        model = MultipleChoiceQuestion
        fields = ['question','image']
        widgets = {
            'question': forms.TextInput(attrs={'size': '60'})}
    
    def __init__(self, *args, **kwargs):
        """
        This method creates text field for each option.
        MAX_CHOICES determines how many choices are available.
        Empty choice fields will not be saved. 
        """
        super(AddMultipleChoiceForm, self).__init__(*args, **kwargs)
        # Create fields for choices: choice_1, choice_2,...
        for x in range(1, MAX_CHOICES+1):
            self.fields["choice_%d" % x] = forms.CharField(label=_("choice %s" % x),
                                                           required=False,)

    def clean(self):
        cleaned_data = super(AddMultipleChoiceForm, self).clean()
        
        # Consolidate choices so there are no holes
        choice_counter = 0
        for x in range(1, MAX_CHOICES+1):
            choice = self.cleaned_data.get("choice_%d" % x)
            if choice:
                self.cleaned_data["choice_%d" % x] = None
                choice_counter += 1
                self.cleaned_data["choice_%d" % choice_counter] = choice
        
        # Require at least REQUIRED_CHOICES choices
        if choice_counter < REQUIRED_CHOICES:
            raise forms.ValidationError("You must provide at least %d choice." % REQUIRED_CHOICES,
                                        code = 'no_choices')
        
        # Check for duplicates
        for i in range(1,choice_counter+1):
            for j in range(i+1, choice_counter+1):
                if (self.cleaned_data["choice_%d" % i]==self.cleaned_data["choice_%d" % j]):
                    raise forms.ValidationError("You have two identical choices.")
        
        return cleaned_data


class MultipleChoiceEditForm(forms.ModelForm):
    """
    Form for editing a multiple choice question. If there are less than MAX_CHOICES choices,
    there is an extra field to add a new choice. If a choice's text is deleted and the form
    is submitted, that choice will be deleted. 
    """
    class Meta:
        model = MultipleChoiceQuestion
        fields = ['question','image']
        widgets = {
            'question': forms.TextInput(attrs={'size': '60'})}
        
    def __init__(self, *args, **kwargs):
        """
        This method creates text field for each choice.  The choice's text value is used as
        initial data.
        Creates extra field for adding a new choice. 
        """    
        super(MultipleChoiceEditForm, self).__init__(*args, **kwargs)   
        i = 1
        for choice in self.instance.multiplechoiceoption_set.all():
            self.fields["choice_%d" % choice.id] = \
                forms.CharField(label=_("choice %s" % i),
                                required=False,
                                initial=choice.text)
            i = i + 1
        if(i <= MAX_CHOICES):
            self.fields["choice_new"] = forms.CharField(label=_("Add A Choice:"), required=False)
  
    def clean(self):
        cleaned_data = super(MultipleChoiceEditForm, self).clean()
        
        # Require at least REQUIRED_CHOICES choices
        choice_counter = 0
        for choice in self.instance.multiplechoiceoption_set.all():
            if self.cleaned_data.get("choice_%d" % choice.id):
                choice_counter += 1
        if self.cleaned_data.get("choice_new"):
            choice_counter += 1
        if choice_counter < REQUIRED_CHOICES:
            raise forms.ValidationError("You must provide at least %d choice." % REQUIRED_CHOICES,
                                        code = 'no_choices')
        
        return cleaned_data

    @transaction.atomic()
    @reversion.create_revision()  
    def save(self):
        """
        Saves the question and all choices.
        Deletes a choice if its field is blank.
        Creates a new choice if 'new_choice' field is not blank.
        
        It is important to save this question and all its options, even if they are unchanged,
        so that they are included in the revision.
        """
        self.instance.question = self.cleaned_data.get('question')
        self.instance.save()
        
        # check to see if each choice still has text in the field, will change if edited,
        # and delete choice if field is blank
        for choice in self.instance.multiplechoiceoption_set.all():
            text = self.cleaned_data.get("choice_%d" % choice.id)
            if text:
                choice.text = text
                choice.save()
            else:
                choice.delete()
        
        # create a new option, if provided
        new_text = self.cleaned_data.get("choice_new")
        if (new_text):
            MultipleChoiceOption.objects.create(question=self.instance, text=new_text)
            
        return self.instance


class QuestionVersionForm(forms.ModelForm):
    
    def get_version_choices(self):
        """
        A list of tuples (i,question)
        
        i is the index in reversion.get_unique_for_object and question is the
        question text at that version
        """
        l = []
        i = 0 
        for version in reversion.get_unique_for_object(self.instance):
            l.append( (i,version.field_dict['question']))
            i+=1
        return l
    
    def __init__(self, *args, **kwargs):
        """
        There is one field, a list of tuples
        """
        super(QuestionVersionForm, self).__init__(*args, **kwargs)
        self.fields['version']=forms.ChoiceField(choices=self.get_version_choices(),
                                                 widget=forms.RadioSelect())
    
    def save(self):
        """
        The data saved in 'version' is an integer that is the selected version's index
        in get_unique_for_object
        """
        index = int(self.cleaned_data.get('version'))
        version_list = reversion.get_unique_for_object(self.instance)
        version_list[index].revert()
        return self.instance


class FreeResponseVersionForm(QuestionVersionForm):
    class Meta:
        model = FreeResponseQuestion
        fields = []

        
class MultipleChoiceVersionForm(QuestionVersionForm):
    class Meta:
        model = MultipleChoiceQuestion
        fields = []
    
    def save(self):
        """
        The data saved in 'version' is an integer that is the selected version's index
        in get_unique_for_object
        """
        index = int(self.cleaned_data.get('version'))
        version_list = reversion.get_unique_for_object(self.instance)
        version_list[index].revision.revert(delete=True)
        return self.instance

class NewResponseSetForm(forms.ModelForm):
    """
    Form in which a distributor provides course info and selects modules
    
    TODO: module selection field
    """
    class Meta:
        model = ResponseSet
        fields = ['course', 'pre_test'] #'modules' ]
        
        #widgets = {
        #    'modules': forms.CheckboxSelectMultiple(),
        #}

class DistributeForm(forms.Form):
    """
    Form for a distributor to provide an expiration date and time and a list of
    student emails.
    
    'recipients' is a custom field MultiEmailField that takes a long text input of emails
    seperated by semicolons and formats it as an array.
    
    'resend' is a custom field ExamResponseChoiceField that is effectively a ModelChoiceField.
    The choices for this field are ExamResponses (in this set) which have been previously
    sent out but have not yet been submitted.
    """
    
    expiration_date = forms.DateField(initial= (date.today() + timedelta(days=7)),
                                      help_text='YYYY-MM-DD')
    
    expiration_time = forms.TimeField(initial= time(23,59,59),
                                      help_text='HH:MM:SS  (use 24-hr clock)')
    
    recipients = MultiEmailField(required=False,
                                 widget=forms.Textarea(attrs={
                                 'placeholder':"seperate with semicolons... \n\nemail1@email.com;\nemail2@email.com"}))
    
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super(DistributeForm, self).__init__(*args, **kwargs)
        pending_exams = self.instance.examresponse_set.filter(submitted__exact=None)
        self.fields["resend"] = ExamResponseChoiceField(queryset=pending_exams,
                                                        required=False,
                                                        widget=forms.CheckboxSelectMultiple())
    
    def clean_recipients(self):
        """
        Check that there has not already been an exam sent to this address. Note that this
        does not check that an email has not been entered twice in the same input.
        """
        data = self.cleaned_data['recipients']
        for email in data:
            if self.instance.examresponse_set.filter(respondent__exact=email):
                raise forms.ValidationError("You have already sent an exam to one or more \
                                            of these addresses.  If you'd like to resend an \
                                            exam, use the checkbox below.")
        return data
    
    def clean(self):
        """
        Check that expiration time is in the future and no more than 100 days from today
        """
        cleaned_data = super(DistributeForm, self).clean()
        expiration_date = cleaned_data.get("expiration_date")
        expiration_time = cleaned_data.get("expiration_time")

        if expiration_date and expiration_time:
            expiration_datetime = datetime.combine(expiration_date, expiration_time)
            if datetime.today() + timedelta(days=100) < expiration_datetime:
                raise forms.ValidationError("Expiration date/time cannot be more than 100 days after today")
            if datetime.today() >= expiration_datetime:
                raise forms.ValidationError("Expiration date/time must be in future")
        return cleaned_data


class BlankForm(forms.Form):
    """
    Used in CleanupView, which doesn't actually need any fields.
    """
    class Meta:
        fields = []

    
class ExamResponseForm(forms.ModelForm):
    """
    Has fields for every question in an exam.  These fields are generated in the __init__()
    method.  After an ExamResponse has been submitted, the save() method updates the
    FreeResponseResponse and QuestionResponseResponse objects with the student's responses.
    """
    class Meta:
        model = ExamResponse
        fields = []
        
    def __init__(self, *args, **kwargs):
        """
        Generate a field for each associated QuestionResponse object.
        """
        super(ExamResponseForm, self).__init__(*args, **kwargs) 
        for response in self.instance.freeresponseresponse_set.all():
            self.fields["FR_response_%d" % response.id] = \
                forms.CharField(label=_(response.question.__unicode__()),
                                required=True,
                                widget=forms.Textarea(),)
        for response in self.instance.multiplechoiceresponse_set.all():
            self.fields["MC_response_%d" % response.id] = \
                forms.ModelChoiceField(label=_(response.question.__unicode__()),
                                       required=True,
                                       queryset=response.question.multiplechoiceoption_set.all(),
                                       empty_label=None,
                                       widget=forms.RadioSelect())
            
    def save(self):
        """
        Save the student's responses.
        """
        for response in self.instance.freeresponseresponse_set.all():
            response.response = self.cleaned_data.get("FR_response_%d" % response.id)
            response.save()
        for response in self.instance.multiplechoiceresponse_set.all():
            response.option = self.cleaned_data.get("MC_response_%d" % response.id)
            response.save()