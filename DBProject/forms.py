# forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.db import transaction
from django.db.models import Q
from .models import Utente, Atleta, Allenatore, PresidenteSquadra, PresidenteRegione, Gara, Partecipazione, Squadra, \
    Regione, Specialita, GaraSpecialita


# Roles selectable on the public registration form (NRD-01).
# Presidents are appointed through the admin interface, never by self-registration.
RUOLI_PUBBLICI = ('ATLETA', 'ALLENATORE')


class RegistrazioneForm(UserCreationForm):
    tipo = forms.ChoiceField(
        choices=[c for c in Utente.TIPO_UTENTE_SCELTE if c[0] in RUOLI_PUBBLICI],
        label="Scegli il tuo ruolo",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_tipo'})
    )
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta(UserCreationForm.Meta):
        model = Utente
        fields = UserCreationForm.Meta.fields + ('tipo', 'email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.tipo = self.cleaned_data["tipo"]
        user.email = self.cleaned_data["email"]

        if commit:
            # Defensive (NRD-06): if profile creation is ever added here,
            # a failure must not leave an orphan user behind.
            with transaction.atomic():
                user.save()

        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Username", widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={'class': 'form-control'}))


class StatoAtletaForm(forms.ModelForm):
    class Meta:
        model = Atleta
        fields = ['stato']
        labels = {'stato': 'Stato di Salute'}
        widgets = {
            'stato': forms.Select(attrs={'class': 'form-select'}),
        }


class AddAtletaForm(forms.Form):
    """Users who can join a team: no athlete profile yet, or a profile not linked to any team."""
    utente = forms.ModelChoiceField(
        queryset=Utente.objects.filter(tipo='ATLETA').filter(
            Q(atleta__isnull=True) | Q(atleta__squadra__isnull=True)
        ),
        label="Seleziona un atleta",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )


class AddAllenatoreForm(forms.Form):
    """Users who can join a team: no coach profile yet, or a profile not linked to any team."""
    utente = forms.ModelChoiceField(
        queryset=Utente.objects.filter(tipo='ALLENATORE').filter(
            Q(allenatore__isnull=True) | Q(allenatore__squadra__isnull=True)
        ),
        label="Seleziona un allenatore",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )


class GaraForm(forms.ModelForm):
    specialita = forms.ModelMultipleChoiceField(
        queryset=Specialita.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Seleziona le specialità",
    )
    sesso = forms.ChoiceField(
        choices=GaraSpecialita.sesso_scelte,
        widget=forms.RadioSelect,
        label="Seleziona il sesso"
    )

    class Meta:
        model = Gara
        fields = ['luogo', 'data_inizio']
        widgets = {
            'luogo': forms.TextInput(attrs={'class': 'form-control'}),
            'data_inizio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class IscrizioneGaraForm(forms.Form):
    atleti_selezionati = forms.ModelMultipleChoiceField(
        queryset=Atleta.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Seleziona gli atleti della squadra da iscrivere"
    )

    def __init__(self, *args, **kwargs):
        gara_specialita = kwargs.pop('gara_specialita')
        allenatore = kwargs.pop('allenatore')
        super().__init__(*args, **kwargs)

        atleti_validi = Atleta.objects.filter(
            squadra=allenatore.squadra,
            stato='SANO'
        ).exclude(
            partecipazione__id_gara=gara_specialita.id_gara,
            partecipazione__id_specialita=gara_specialita.id_specialita
        )
        self.fields['atleti_selezionati'].queryset = atleti_validi


class RisultatoForm(forms.ModelForm):
    class Meta:
        model = Partecipazione
        fields = ['risultato', 'stato_iscrizione']
        labels = {
            'risultato': 'Risultato (es. 00:01:23.45)',
            'stato_iscrizione': 'Stato',
        }
        widgets = {
            'risultato': forms.TextInput(attrs={'class': 'form-control'}),
            'stato_iscrizione': forms.Select(attrs={'class': 'form-select'}),
        }