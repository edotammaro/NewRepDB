from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .forms import RegistrazioneForm
from .models import Utente, Regione, Squadra, PresidenteRegione, PresidenteSquadra

PASSWORD = "Zq7!vLm29-tRw"


def dati_registrazione(username, tipo, **extra):
    dati = {
        "username": username,
        "email": username + "@example.com",
        "password1": PASSWORD,
        "password2": PASSWORD,
        "tipo": tipo,
    }
    dati.update(extra)
    return dati


class RegistrazioneRuoliTests(TestCase):
    """NRD-01: la registrazione pubblica non deve assegnare ruoli apicali."""

    def registra(self, dati):
        return self.client.post(reverse("register"), dati)

    def test_il_form_offre_solo_ruoli_di_base(self):
        valori = {v for v, _ in RegistrazioneForm().fields["tipo"].choices if v}
        self.assertEqual(valori, {"ATLETA", "ALLENATORE"})

    def test_ruoli_di_base_si_registrano(self):
        for tipo in ("ATLETA", "ALLENATORE"):
            with self.subTest(tipo=tipo):
                username = "utente_" + tipo.lower()
                risposta = self.registra(dati_registrazione(username, tipo))
                self.assertRedirects(risposta, reverse("login"), fetch_redirect_response=False)
                self.assertEqual(Utente.objects.get(username=username).tipo, tipo)

    def test_presidente_di_regione_non_si_registra(self):
        regione = Regione.objects.create(nome="Lazio")
        risposta = self.registra(dati_registrazione("falso_pres_reg", "PRES_REGIONE", regione=regione.pk))
        self.assertEqual(risposta.status_code, 200)
        self.assertFalse(Utente.objects.filter(username="falso_pres_reg").exists())
        self.assertFalse(PresidenteRegione.objects.exists())

    def test_presidente_di_squadra_non_si_registra(self):
        risposta = self.registra(dati_registrazione("falso_pres_sq", "PRES_SQUADRA", nome_squadra="Squadra nuova"))
        self.assertEqual(risposta.status_code, 200)
        self.assertFalse(Utente.objects.filter(username="falso_pres_sq").exists())
        self.assertFalse(PresidenteSquadra.objects.exists())
        self.assertFalse(Squadra.objects.filter(nome="Squadra nuova").exists())

    def test_nessun_subentro_in_squadra_senza_presidente(self):
        squadra = Squadra.objects.create(nome="Squadra senza presidente")
        self.registra(dati_registrazione("intruso", "PRES_SQUADRA", nome_squadra=squadra.nome))
        self.assertFalse(Utente.objects.filter(username="intruso").exists())
        self.assertFalse(PresidenteSquadra.objects.filter(squadra=squadra).exists())


class RegistrazioneAtomicitaTests(TransactionTestCase):
    """NRD-06: una registrazione fallita non deve lasciare utenti orfani."""

    def test_registrazione_fallita_non_lascia_utenti_orfani(self):
        presidente = Utente.objects.create_user(
            username="presidente", email="presidente@example.com", password=PASSWORD, tipo="PRES_SQUADRA"
        )
        squadra = Squadra.objects.create(nome="Squadra occupata")
        PresidenteSquadra.objects.create(utente=presidente, squadra=squadra)

        self.client.raise_request_exception = False
        self.client.post(
            reverse("register"),
            dati_registrazione("nuovo", "PRES_SQUADRA", nome_squadra=squadra.nome),
        )
        self.assertFalse(Utente.objects.filter(username="nuovo").exists())
