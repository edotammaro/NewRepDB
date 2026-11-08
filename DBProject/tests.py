from datetime import timedelta

from django.test import Client, TestCase, TransactionTestCase
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


class RiaggiuntaMembriTests(AzioniDistruttiveBase):
    """A member unlinked from a team can be added again; members of other teams cannot be taken."""

    def aggiungi_atleta(self, utente):
        return self.client.post(reverse("dashboard_pres_squadra"), {"add_atleta": "1", "utente": utente.pk})

    def aggiungi_allenatore(self, utente):
        return self.client.post(reverse("dashboard_pres_squadra"), {"add_allenatore": "1", "utente": utente.pk})

    def test_atleta_rimosso_si_puo_riaggiungere(self):
        self.client.force_login(self.presidente_user)
        self.client.post(reverse("rimuovi_membro", args=[self.atleta.pk, "atleta"]))
        self.aggiungi_atleta(self.atleta_user)
        self.assertEqual(Atleta.objects.filter(utente=self.atleta_user).count(), 1)
        self.assertEqual(Atleta.objects.get(utente=self.atleta_user).squadra, self.squadra)
        self.assertTrue(Partecipazione.objects.filter(pk=self.iscrizione.pk).exists())

    def test_allenatore_rimosso_si_puo_riaggiungere(self):
        self.client.force_login(self.presidente_user)
        self.client.post(reverse("rimuovi_membro", args=[self.allenatore.pk, "allenatore"]))
        self.aggiungi_allenatore(self.allenatore_user)
        self.assertEqual(Allenatore.objects.filter(utente=self.allenatore_user).count(), 1)
        self.assertEqual(Allenatore.objects.get(utente=self.allenatore_user).squadra, self.squadra)

    def test_utente_senza_profilo_si_aggiunge_come_atleta(self):
        nuovo = crea_utente("atleta_nuovo", "ATLETA")
        self.client.force_login(self.presidente_user)
        self.aggiungi_atleta(nuovo)
        self.assertEqual(Atleta.objects.get(utente=nuovo).squadra, self.squadra)

    def test_non_si_porta_via_un_atleta_di_un_altra_squadra(self):
        squadra_b = Squadra.objects.create(nome="Squadra B")
        atleta_b = Atleta.objects.create(utente=crea_utente("atleta_b", "ATLETA"), squadra=squadra_b)
        self.client.force_login(self.presidente_user)
        self.aggiungi_atleta(atleta_b.utente)
        atleta_b.refresh_from_db()
        self.assertEqual(atleta_b.squadra, squadra_b)

    def test_non_si_porta_via_un_allenatore_di_un_altra_squadra(self):
        squadra_b = Squadra.objects.create(nome="Squadra B")
        allenatore_b = Allenatore.objects.create(utente=crea_utente("coach_b", "ALLENATORE"), squadra=squadra_b)
        self.client.force_login(self.presidente_user)
        self.aggiungi_allenatore(allenatore_b.utente)
        allenatore_b.refresh_from_db()
        self.assertEqual(allenatore_b.squadra, squadra_b)


class LockoutLoginTests(TestCase):
    """NRD-04: the failed-login lockout must not let an attacker lock other people out."""

    SBAGLIATA = "password-sbagliata"

    def crea_account(self, nome):
        return crea_utente(nome, "ATLETA")

    def tenta(self, username, password, ip):
        client = Client()
        client.post(reverse("login"), {"username": username, "password": password}, REMOTE_ADDR=ip)
        return client

    def autenticato(self, client):
        return "_auth_user_id" in client.session

    def fallisci(self, username, ip, volte=5):
        for _ in range(volte):
            self.tenta(username, self.SBAGLIATA, ip)

    def test_un_account_non_si_blocca_da_un_altro_indirizzo(self):
        self.crea_account("lock_vittima_1")
        self.fallisci("lock_vittima_1", "10.0.0.1")
        legittimo = self.tenta("lock_vittima_1", PASSWORD, "10.0.0.2")
        self.assertTrue(self.autenticato(legittimo))

    def test_stesso_indirizzo_e_account_restano_bloccati(self):
        self.crea_account("lock_vittima_2")
        self.fallisci("lock_vittima_2", "10.0.0.1")
        attaccante = self.tenta("lock_vittima_2", PASSWORD, "10.0.0.1")
        self.assertFalse(self.autenticato(attaccante))

    def test_altro_account_dallo_stesso_indirizzo_non_e_bloccato(self):
        self.crea_account("lock_vittima_3")
        self.crea_account("lock_altro_3")
        self.fallisci("lock_vittima_3", "10.0.0.1")
        altro = self.tenta("lock_altro_3", PASSWORD, "10.0.0.1")
        self.assertTrue(self.autenticato(altro))

    def test_un_accesso_riuscito_azzera_i_fallimenti(self):
        self.crea_account("lock_vittima_4")
        self.fallisci("lock_vittima_4", "10.0.0.1", volte=4)
        self.assertTrue(self.autenticato(self.tenta("lock_vittima_4", PASSWORD, "10.0.0.1")))
        self.fallisci("lock_vittima_4", "10.0.0.1", volte=4)
        self.assertTrue(self.autenticato(self.tenta("lock_vittima_4", PASSWORD, "10.0.0.1")))

    def tenta_con_xff(self, username, password, ip, xff):
        client = Client()
        client.post(
            reverse("login"),
            {"username": username, "password": password},
            REMOTE_ADDR=ip,
            HTTP_X_FORWARDED_FOR=xff,
        )
        return client

    def test_x_forwarded_for_falsificato_non_aggira_il_blocco(self):
        """An attacker rotating X-Forwarded-For must stay locked out (client IP = REMOTE_ADDR)."""
        self.crea_account("lock_vittima_5")
        for i in range(5):
            self.tenta_con_xff("lock_vittima_5", self.SBAGLIATA, "10.0.0.1", "203.0.113." + str(i + 1))
        attaccante = self.tenta_con_xff("lock_vittima_5", PASSWORD, "10.0.0.1", "203.0.113.99")
        self.assertFalse(self.autenticato(attaccante))

    def test_x_forwarded_for_dell_attaccante_non_blocca_un_altro_indirizzo(self):
        """The header must not count: a victim with a different REMOTE_ADDR is not locked out."""
        self.crea_account("lock_vittima_6")
        for _ in range(5):
            self.tenta_con_xff("lock_vittima_6", self.SBAGLIATA, "10.0.0.1", "10.0.0.2")
        legittimo = self.tenta_con_xff("lock_vittima_6", PASSWORD, "10.0.0.2", "10.0.0.1")
        self.assertTrue(self.autenticato(legittimo))


class NessunaSquadraTests(AzioniDistruttiveBase):
    """NRD-15: a president or coach with squadra=None must not see or touch unassigned athletes."""

    def setUp(self):
        self.client.raise_request_exception = False

    def presidente_orfano(self):
        utente = crea_utente("pres_orfano_15", "PRES_SQUADRA")
        PresidenteSquadra.objects.create(utente=utente, squadra=None)
        return utente

    def allenatore_orfano(self):
        utente = crea_utente("coach_orfano_15", "ALLENATORE")
        Allenatore.objects.create(utente=utente, squadra=None)
        return utente

    def iscrizione_svincolato(self):
        return Partecipazione.objects.create(
            id_atleta=self.svincolato, id_gara=self.gara, id_specialita=self.specialita
        )

    def test_dashboard_presidente_senza_squadra_e_negata(self):
        self.client.force_login(self.presidente_orfano())
        risposta = self.client.get(reverse("dashboard_pres_squadra"))
        self.assertEqual(risposta.status_code, 403)

    def test_dashboard_allenatore_senza_squadra_e_negata(self):
        self.client.force_login(self.allenatore_orfano())
        risposta = self.client.get(reverse("dashboard_allenatore"))
        self.assertEqual(risposta.status_code, 403)

    def test_allenatore_senza_squadra_non_apre_il_risultato_di_uno_svincolato(self):
        iscrizione = self.iscrizione_svincolato()
        self.client.force_login(self.allenatore_orfano())
        risposta = self.client.get(reverse("inserisci_risultato", args=[iscrizione.pk]))
        self.assertEqual(risposta.status_code, 403)

    def test_allenatore_senza_squadra_non_modifica_il_risultato_di_uno_svincolato(self):
        iscrizione = self.iscrizione_svincolato()
        self.client.force_login(self.allenatore_orfano())
        risposta = self.client.post(
            reverse("inserisci_risultato", args=[iscrizione.pk]), {"risultato": "10.50"}
        )
        self.assertEqual(risposta.status_code, 403)
        iscrizione.refresh_from_db()
        self.assertIsNone(iscrizione.risultato)
