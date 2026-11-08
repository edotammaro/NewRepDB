from datetime import timedelta

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.timezone import now

from .forms import RegistrazioneForm
from .models import (
    Allenatore, Atleta, Gara, GaraSpecialita, Partecipazione, PresidenteRegione,
    PresidenteSquadra, Regione, Specialita, Squadra, Utente,
)

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


def crea_utente(username, tipo):
    return Utente.objects.create_user(
        username=username, email=username + "@example.com", password=PASSWORD, tipo=tipo
    )


class AzioniDistruttiveBase(TestCase):
    """Shared data: a team with president, coach and athlete, plus a future race with one enrollment."""

    @classmethod
    def setUpTestData(cls):
        cls.squadra = Squadra.objects.create(nome="Squadra A")
        cls.presidente_user = crea_utente("pres_a", "PRES_SQUADRA")
        PresidenteSquadra.objects.create(utente=cls.presidente_user, squadra=cls.squadra)
        cls.allenatore_user = crea_utente("coach_a", "ALLENATORE")
        cls.allenatore = Allenatore.objects.create(utente=cls.allenatore_user, squadra=cls.squadra)
        cls.atleta_user = crea_utente("atleta_a", "ATLETA")
        cls.atleta = Atleta.objects.create(utente=cls.atleta_user, squadra=cls.squadra)
        cls.svincolato_user = crea_utente("svincolato", "ATLETA")
        cls.svincolato = Atleta.objects.create(utente=cls.svincolato_user, squadra=None)

        regione = Regione.objects.create(nome="Lazio")
        pres_reg_user = crea_utente("pres_reg", "PRES_REGIONE")
        pres_reg = PresidenteRegione.objects.create(utente=pres_reg_user, regione=regione)
        cls.gara = Gara.objects.create(
            presidente_regione=pres_reg, luogo="Roma", data_inizio=now().date() + timedelta(days=10)
        )
        cls.specialita = Specialita.objects.create(nome="100m")
        GaraSpecialita.objects.create(id_gara=cls.gara, id_specialita=cls.specialita, sesso="M")
        cls.iscrizione = Partecipazione.objects.create(
            id_atleta=cls.atleta, id_gara=cls.gara, id_specialita=cls.specialita
        )


class AzioniSoloPostTests(AzioniDistruttiveBase):
    """NRD-02: state-changing actions must not run on GET."""

    def test_logout_via_get_non_esegue_il_logout(self):
        self.client.force_login(self.atleta_user)
        risposta = self.client.get(reverse("logout"))
        self.assertEqual(risposta.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_via_post_funziona(self):
        self.client.force_login(self.atleta_user)
        risposta = self.client.post(reverse("logout"))
        self.assertRedirects(risposta, reverse("home"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rimuovi_membro_via_get_non_cancella(self):
        self.client.force_login(self.presidente_user)
        url = reverse("rimuovi_membro", args=[self.atleta.pk, "atleta"])
        risposta = self.client.get(url)
        self.assertEqual(risposta.status_code, 405)
        self.assertTrue(Atleta.objects.filter(pk=self.atleta.pk).exists())

    def test_rimuovi_iscrizione_via_get_non_cancella(self):
        self.client.force_login(self.allenatore_user)
        url = reverse("rimuovi_iscrizione", args=[self.iscrizione.pk])
        risposta = self.client.get(url)
        self.assertEqual(risposta.status_code, 405)
        self.assertTrue(Partecipazione.objects.filter(pk=self.iscrizione.pk).exists())

    def test_rimuovi_iscrizione_via_post_funziona(self):
        self.client.force_login(self.allenatore_user)
        url = reverse("rimuovi_iscrizione", args=[self.iscrizione.pk])
        risposta = self.client.post(url)
        self.assertRedirects(risposta, reverse("dashboard_allenatore"), fetch_redirect_response=False)
        self.assertFalse(Partecipazione.objects.filter(pk=self.iscrizione.pk).exists())

    def test_pagina_allenatore_usa_form_post_e_non_link(self):
        self.client.force_login(self.allenatore_user)
        risposta = self.client.get(reverse("dashboard_allenatore"))
        self.assertEqual(risposta.status_code, 200)
        html = risposta.content.decode()
        rimozione = reverse("rimuovi_iscrizione", args=[self.iscrizione.pk])
        logout = reverse("logout")
        self.assertIn('action="' + rimozione + '"', html)
        self.assertNotIn('href="' + rimozione + '"', html)
        self.assertIn('action="' + logout + '"', html)
        self.assertNotIn('href="' + logout + '"', html)


class RimozioneMembriTests(AzioniDistruttiveBase):
    """NRD-03: removing a member unlinks it from the team, it does not delete the profile."""

    def test_rimuovere_un_atleta_lo_scollega_senza_cancellarlo(self):
        self.client.force_login(self.presidente_user)
        self.client.post(reverse("rimuovi_membro", args=[self.atleta.pk, "atleta"]))
        self.assertTrue(Atleta.objects.filter(pk=self.atleta.pk).exists())
        self.assertTrue(Partecipazione.objects.filter(pk=self.iscrizione.pk).exists())
        self.assertIsNone(Atleta.objects.get(pk=self.atleta.pk).squadra)

    def test_rimuovere_un_allenatore_lo_scollega_senza_cancellarlo(self):
        self.client.force_login(self.presidente_user)
        self.client.post(reverse("rimuovi_membro", args=[self.allenatore.pk, "allenatore"]))
        self.assertTrue(Allenatore.objects.filter(pk=self.allenatore.pk).exists())
        self.assertIsNone(Allenatore.objects.get(pk=self.allenatore.pk).squadra)

    def test_presidente_con_squadra_non_tocca_gli_svincolati(self):
        self.client.force_login(self.presidente_user)
        self.client.post(reverse("rimuovi_membro", args=[self.svincolato.pk, "atleta"]))
        self.assertTrue(Atleta.objects.filter(pk=self.svincolato.pk).exists())

    def test_presidente_senza_squadra_non_tocca_gli_svincolati(self):
        orfano = crea_utente("pres_orfano", "PRES_SQUADRA")
        PresidenteSquadra.objects.create(utente=orfano, squadra=None)
        self.client.force_login(orfano)
        self.client.post(reverse("rimuovi_membro", args=[self.svincolato.pk, "atleta"]))
        self.assertTrue(Atleta.objects.filter(pk=self.svincolato.pk).exists())


class RimozioneIscrizioneTests(AzioniDistruttiveBase):
    """NRD-10: an enrollment of an athlete without a team must not cause a 500."""

    def test_iscrizione_di_atleta_senza_squadra_non_da_500(self):
        iscrizione = Partecipazione.objects.create(
            id_atleta=self.svincolato, id_gara=self.gara, id_specialita=self.specialita
        )
        self.client.force_login(self.allenatore_user)
        self.client.raise_request_exception = False
        risposta = self.client.post(reverse("rimuovi_iscrizione", args=[iscrizione.pk]))
        self.assertNotEqual(risposta.status_code, 500)
        self.assertTrue(Partecipazione.objects.filter(pk=iscrizione.pk).exists())
