from django import forms
from django.forms.formsets import formset_factory, BaseFormSet

from nodemanager.models import ConceptAtom

class AtomForm(forms.Form):

    pk = forms.IntegerField(widget=forms.HiddenInput(attrs={'readonly': True}),
                            required=False)

    text = forms.CharField(max_length=140,
                           widget=forms.Textarea(attrs={'cols': 70, 'rows': 2}))

    def clean_text(self):
        data = self.cleaned_data['text']
        if not data or len(data) < 1:
            raise forms.ValidationError("Can't have an empty Concept Atom!")

        return data

class CreateMergeForm(forms.Form):

    free_atoms = forms.ModelMultipleChoiceField(
        queryset=ConceptAtom.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    merged_atoms = forms.ModelChoiceField(
        queryset=ConceptAtom.objects.none(),
        widget=forms.RadioSelect,
        required=False
    )
    new_atom_name = forms.CharField(max_length=140, required=False)

    add_merge_id = 'add merge'
    subtract_merge_id = 'subtract merge'

    def __init__(self, *args, **kwargs):

        node = kwargs.pop('node')

        super(CreateMergeForm, self).__init__(*args, **kwargs)

        self.fields['free_atoms'].queryset = ConceptAtom.get_unmerged_atoms(node)
        self.fields['merged_atoms'].queryset = ConceptAtom.get_final_atoms(node)

    def clean(self):

        cleaned_data = super(CreateMergeForm, self).clean()
        new_atom_name = cleaned_data.get('new_atom_name')
        merged_atom_choice = cleaned_data.get('merged_atoms')

        if (new_atom_name and merged_atom_choice):
            raise forms.ValidationError("Must either pick or create an atom to merge, cannot do both.")
        elif (not new_atom_name and not merged_atom_choice):
            raise forms.ValidationError("Must pick or create an atom to merge with, none entered.")

        return cleaned_data


class UpdateMergeForm(forms.Form):

     pk = forms.IntegerField(widget=forms.HiddenInput(attrs={'readonly': True}))

     choices = forms.ModelMultipleChoiceField(
         queryset=ConceptAtom.objects.none(), #initial qset is empty
         widget=forms.CheckboxSelectMultiple,
         required=False)
     atom_name = None
     delete = forms.BooleanField(label="Delete and Unmerge All",
                                 required=False)

     def __init__(self, *args, **kwargs):

         super(UpdateMergeForm, self).__init__(*args, **kwargs)

         #dynamically find the choice qset for the corresponding concept atom
         my_pk = self['pk'].value()
         self.fields['choices'].queryset = ConceptAtom.objects.filter(merged_atoms__pk=my_pk)
         self.atom_name = ConceptAtom.objects.filter(pk=my_pk).get().text

class BaseUpdateMergeFormset(BaseFormSet):

    def clean(self):

        if any(self.errors): #if there are any individual errors, exit
            return

        for form in self.forms:
            delete = form.cleaned_data.get('delete')
            choice_qset = form.cleaned_data.get('choices')

            # if at any point we have a deletion or non-empty qset,
            # form cannot be empty
            if delete or choice_qset:
                return

        raise forms.ValidationError("Did not enter anything to edit or remove.")

UpdateMergeFormSet = formset_factory(UpdateMergeForm,
                                     formset=BaseUpdateMergeFormset,
                                     extra=0)
