from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError
from django.contrib import messages
from .forms import RegistrazioneForm, LoginForm, AddAtletaForm, AddAllenatoreForm, GaraForm, IscrizioneGaraForm, \
    StatoAtletaForm, RisultatoForm
from .models import Utente, Atleta, Allenatore, PresidenteSquadra, PresidenteRegione, Squadra, Gara, GaraSpecialita, \
    Specialita, Partecipazione
import time
from django.utils.timezone import now
from datetime import timedelta
import logging

def is_atleta(user):
    return user.is_authenticated and user.tipo == 'ATLETA'


def is_allenatore(user):
    return user.is_authenticated and user.tipo == 'ALLENATORE'


def is_pres_squadra(user):
    return user.is_authenticated and user.tipo == 'PRES_SQUADRA'


def is_pres_regione(user):
    return user.is_authenticated and user.tipo == 'PRES_REGIONE'


def home_view(request):
    return render(request, 'DBProject/home.html')


def register_view(request):
    if request.method == "POST":
        form = RegistrazioneForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Utente registrato con successo!")
            return redirect('login')
        else:
            messages.error(request, "Errore nella registrazione. Controlla i dati inseriti.")
    else:
        form = RegistrazioneForm()
    return render(request, 'DBProject/register.html', {'form': form})


# Dizionario per tenere traccia dei tentativi di login falliti
FALLISMENTI_LOGIN = {}
# Numero massimo di tentativi prima del blocco
MAX_TENTATIVI = 5
# Tempo di blocco in secondi (es. 5 minuti)
LOCKOUT_TIME = 5 * 60


def login_view(request):
    if request.method == 'POST':
        # Istanzia il form correttamente, passando request e data
        form = LoginForm(request=request, data=request.POST)
        username = request.POST.get('username')

        # Controllo immediato del blocco, prima di ogni altra operazione
        now = time.time()
        if username and username in FALLISMENTI_LOGIN:
            tentativi_falliti, ultimo_tentativo = FALLISMENTI_LOGIN[username]
            if tentativi_falliti >= MAX_TENTATIVI and (now - ultimo_tentativo) < LOCKOUT_TIME:
                remaining_time = int(LOCKOUT_TIME - (now - ultimo_tentativo))
                messages.error(request, f"Troppi tentativi falliti per l'utente '{username}'. Riprova tra {remaining_time} secondi.")
                return render(request, 'DBProject/login.html', {'form': form})

        # Processiamo il form
        if form.is_valid():
            user = form.get_user() # Usa form.get_user() che gestisce già l'autenticazione

            if user is not None:
                login(request, user)
                # Resetta il contatore in caso di successo
                if username in FALLISMENTI_LOGIN:
                    del FALLISMENTI_LOGIN[username]
                messages.success(request, f"Benvenuto, {username}!")
                return redirect('dashboard')
            else:
                # Questo blocco non dovrebbe mai essere raggiunto se form.is_valid() è vero
                # ma lo manteniamo per sicurezza.
                messages.error(request, 'Username o password non validi.')
        else:
            # Qui il form è invalido (es. username/password vuoti)
            if username:
                if username not in FALLISMENTI_LOGIN:
                    FALLISMENTI_LOGIN[username] = [0, now]
                FALLISMENTI_LOGIN[username][0] += 1
                FALLISMENTI_LOGIN[username][1] = now
            messages.error(request, 'Credenziali non valide. Riprova.')
    else:
        form = LoginForm()

    return render(request, 'DBProject/login.html', {'form': form})

@login_required(login_url='/login/')
def logout_view(request):
    logout(request)
    return redirect('home')


@login_required(login_url='/login/')
def dashboard_view(request):
    if is_atleta(request.user):
        try:
            atleta_obj = Atleta.objects.get(utente=request.user)
            form_stato = StatoAtletaForm(instance=atleta_obj)

            # Funzionalità 1: Calendario Gare completo con stato di iscrizione
            gare_specialita = GaraSpecialita.objects.all().order_by('id_gara__data_inizio')

            # Funzionalità 2, 3 e 4: Visualizzazione delle iscrizioni attuali e dei risultati
            iscrizioni_atleta = Partecipazione.objects.filter(id_atleta=atleta_obj).select_related(
                'id_gara', 'id_specialita'
            ).order_by('id_gara__data_inizio')

            # Prepara i dati del calendario in modo più efficiente per il template
            calendario_con_stato = []
            for gara_spec in gare_specialita:
                is_iscritto = iscrizioni_atleta.filter(
                    id_gara=gara_spec.id_gara,
                    id_specialita=gara_spec.id_specialita
                ).exists()
                calendario_con_stato.append({
                    'gara_specialita': gara_spec,
                    'is_iscritto': is_iscritto
                })

            context = {
                'atleta': atleta_obj,
                'tipo_utente': 'ATLETA',
                'form_stato': form_stato,
                'iscrizioni_atleta': iscrizioni_atleta,
                'calendario_con_stato': calendario_con_stato,
            }
            return render(request, 'DBProject/dashboard_atleta.html', context)
        except Atleta.DoesNotExist:
            messages.info(request,
                          "Sei registrato come atleta ma non sei ancora stato assegnato a una squadra. Attendi che il presidente di una squadra ti aggiunga.")
            return render(request, 'DBProject/dashboard.html', {'tipo_utente': 'ATLETA'})
    elif is_allenatore(request.user):
        return redirect('dashboard_allenatore')
    elif is_pres_squadra(request.user):
        return redirect('dashboard_pres_squadra')
    elif is_pres_regione(request.user):
        return redirect('dashboard_pres_regione')
    return render(request, 'DBProject/dashboard.html')


@login_required(login_url='/login/')
@user_passes_test(is_pres_squadra)
def dashboard_pres_squadra(request):
    # Retrieve the president and their associated team
    presidente = get_object_or_404(PresidenteSquadra, utente=request.user)
    squadra = presidente.squadra
    allenatori = squadra.allenatori.all()
    atleti = squadra.atleti.all()

    # Fetch future and past competitions
    gare_future = Gara.objects.filter(data_inizio__gte=now()).order_by('data_inizio')
    gare_passate = Gara.objects.filter(data_fine__lt=now()).order_by('-data_fine')

    # Populate specialita_per_gara
    specialita_per_gara = {
        gara.pk: GaraSpecialita.objects.filter(id_gara=gara) for gara in gare_future
    }

    # Initialize forms for adding athletes and coaches
    add_atleta_form = AddAtletaForm(initial={'squadra': squadra.pk})
    add_allenatore_form = AddAllenatoreForm(initial={'squadra': squadra.pk})

    if request.method == 'POST':
        # Handle adding an athlete
        if 'add_atleta' in request.POST:
            add_atleta_form = AddAtletaForm(request.POST)
            if add_atleta_form.is_valid():
                try:
                    atleta = add_atleta_form.save(commit=False)
                    atleta.squadra = squadra
                    atleta.save()
                    messages.success(request, f"Atleta '{atleta.utente.username}' aggiunto con successo.")
                except IntegrityError:
                    messages.error(request, "Questo utente è già un atleta e non può essere aggiunto nuovamente.")
            else:
                messages.error(request, "Errore nel form per aggiungere un atleta.")
            return redirect('dashboard_pres_squadra')

        # Handle adding a coach
        if 'add_allenatore' in request.POST:
            add_allenatore_form = AddAllenatoreForm(request.POST)
            if add_allenatore_form.is_valid():
                try:
                    allenatore = add_allenatore_form.save(commit=False)
                    allenatore.squadra = squadra
                    allenatore.save()
                    messages.success(request, f"Allenatore '{allenatore.utente.username}' aggiunto con successo.")
                except IntegrityError:
                    messages.error(request, "Questo utente è già un allenatore e non può essere aggiunto nuovamente.")
            else:
                messages.error(request, "Errore nel form per aggiungere un allenatore.")
            return redirect('dashboard_pres_squadra')

    # Prepare the context for rendering the template
    context = {
        'presidente': presidente,
        'squadra': squadra,
        'allenatori': allenatori,
        'atleti': atleti,
        'gare_future': gare_future,
        'gare_passate': gare_passate,
        'specialita_per_gara': specialita_per_gara,
        'add_atleta_form': add_atleta_form,
        'add_allenatore_form': add_allenatore_form,
        'tipo_utente': 'PRES_SQUADRA',
    }
    return render(request, 'DBProject/dashboard_pres_squadra.html', context)


logger = logging.getLogger(__name__)

@login_required(login_url='/login/')
@user_passes_test(is_allenatore)
def dashboard_allenatore(request):
    allenatore = get_object_or_404(Allenatore, utente=request.user)
    squadra = allenatore.squadra
    atleti_squadra = Atleta.objects.filter(squadra=squadra)

    gare_passate = Gara.objects.filter(data_fine__lt=now()).order_by('data_fine')
    gare_future = Gara.objects.filter(data_fine__gte=now()).order_by('data_inizio')

    forms_iscrizione = {}
    iscrizioni_per_specialita = {}
    specialita_per_gara = {} # Initialize an empty dictionary here

    for gara in gare_future:
        gare_specialita = GaraSpecialita.objects.filter(id_gara=gara)
        specialita_per_gara[gara.pk] = gare_specialita
        for gs in gare_specialita:
            forms_iscrizione[gs.pk] = IscrizioneGaraForm(gara_specialita=gs, allenatore=allenatore)
            iscrizioni_per_specialita[gs.pk] = Partecipazione.objects.filter(
                id_gara=gs.id_gara,
                id_specialita=gs.id_specialita,
                id_atleta__squadra=squadra  # Filter by the coach's team
            ).select_related('id_atleta__utente').order_by('id_atleta__utente__username')

    context = {
        'allenatore': allenatore,
        'squadra': squadra,
        'atleti_squadra': atleti_squadra,
        'tipo_utente': 'ALLENATORE',
        'gare_passate': gare_passate,
        'gare_future': gare_future,
        'forms_iscrizione': forms_iscrizione,
        'iscrizioni_per_specialita': iscrizioni_per_specialita,
        'specialita_per_gara': specialita_per_gara,
    }
    return render(request, 'DBProject/dashboard_allenatore.html', context)


@login_required(login_url='/login/')
@user_passes_test(is_pres_squadra)
def rimuovi_membro(request, membro_id, tipo_membro):
    squadra_utente = request.user.presidentesquadra.squadra

    if tipo_membro == 'atleta':
        membro = get_object_or_404(Atleta, pk=membro_id, squadra=squadra_utente)
        membro.delete()
        messages.success(request, f"L'atleta '{membro.utente.username}' è stato rimosso dalla squadra.")
    elif tipo_membro == 'allenatore':
        membro = get_object_or_404(Allenatore, pk=membro_id, squadra=squadra_utente)
        membro.delete()
        messages.success(request, f"L'allenatore '{membro.utente.username}' è stato rimosso dalla squadra.")
    else:
        messages.error(request, "Tipo di membro non valido.")

    return redirect('dashboard_pres_squadra')


@login_required(login_url='/login/')
@user_passes_test(is_pres_regione)
def crea_gara_view(request):
    if request.method == 'POST':
        form = GaraForm(request.POST)
        if form.is_valid():
            gara = form.save(commit=False)
            presidente_regione = get_object_or_404(PresidenteRegione, utente=request.user)
            gara.presidente_regione = presidente_regione
            gara.save()

            specialita_selezionate = form.cleaned_data['specialita']
            sesso_selezionato = form.cleaned_data['sesso']

            for specialita in specialita_selezionate:
                GaraSpecialita.objects.create(
                    id_gara=gara,
                    id_specialita=specialita,
                    sesso=sesso_selezionato
                )

            messages.success(request, f"Gara '{gara.luogo}' creata con successo!")
            return redirect('dashboard')
    else:
        form = GaraForm()

    context = {
        'form': form,
        'tipo_utente': 'PRES_REGIONE',
    }
    return render(request, 'DBProject/crea_gara.html', context)


@login_required(login_url='/login/')
@user_passes_test(is_pres_regione)
def rimuovi_gara_view(request, gara_id):
    gara = get_object_or_404(Gara, pk=gara_id)
    if gara.presidente_regione.utente != request.user:
        messages.error(request, "Non hai il permesso di rimuovere questa gara.")
        return redirect('dashboard')

    if request.method == 'POST':
        gara.delete()
        messages.success(request, f"La gara a '{gara.luogo}' è stata rimossa con successo.")

    return redirect('dashboard')


@login_required(login_url='/login/')
@user_passes_test(is_allenatore)
def iscrivi_atleti_gara(request, gara_specialita_id):
    allenatore = get_object_or_404(Allenatore, utente=request.user)
    gara_specialita = get_object_or_404(GaraSpecialita, pk=gara_specialita_id)

    if request.method == 'POST':
        form = IscrizioneGaraForm(request.POST, gara_specialita=gara_specialita, allenatore=allenatore)

        if form.is_valid():
            atleti_selezionati = form.cleaned_data['atleti_selezionati']

            iscrizioni_create = 0
            for atleta in atleti_selezionati:
                # Ensure the athlete belongs to the coach's team
                if atleta.squadra != allenatore.squadra:
                    messages.error(request, f"L'atleta '{atleta.utente.username}' non appartiene alla tua squadra.")
                    continue

                try:
                    Partecipazione.objects.create(
                        id_atleta=atleta,
                        id_gara=gara_specialita.id_gara,
                        id_specialita=gara_specialita.id_specialita,
                        stato_iscrizione='ISCRITTO'
                    )
                    iscrizioni_create += 1
                except IntegrityError:
                    messages.warning(request, f"L'atleta '{atleta.utente.username}' era già iscritto alla gara.")

            if iscrizioni_create > 0:
                messages.success(request, f"Iscrizione di {iscrizioni_create} atleti alla gara completata con successo.")
        else:
            messages.error(request, "Errore durante l'iscrizione. Controlla i dati del form.")

    return redirect('dashboard_allenatore')


@login_required(login_url='/login/')
@user_passes_test(is_allenatore)
def rimuovi_iscrizione(request, partecipazione_id):
    iscrizione = get_object_or_404(Partecipazione, pk=partecipazione_id)

    # Check if the coach has permission to remove this registration
    if iscrizione.id_atleta.squadra.allenatori.filter(utente=request.user).exists():
        atleta_nome = iscrizione.id_atleta.utente.username
        iscrizione.delete()
        messages.success(request, f"L'atleta '{atleta_nome}' è stato rimosso dalla gara con successo.")
    else:
        messages.error(request, "Non hai i permessi per rimuovere questa iscrizione.")

    return redirect('dashboard_allenatore')



@login_required(login_url='/login/')
@user_passes_test(is_atleta)
def aggiorna_stato_atleta(request):
    if request.method == 'POST':
        atleta = get_object_or_404(Atleta, utente=request.user)
        form = StatoAtletaForm(request.POST, instance=atleta)
        if form.is_valid():
            nuovo_stato = form.cleaned_data['stato']
            if nuovo_stato == 'INFORTUNATO' and atleta.stato != 'INFORTUNATO':
                partecipazioni_rimosse = Partecipazione.objects.filter(id_atleta=atleta).delete()
                if partecipazioni_rimosse[0] > 0:
                    messages.warning(request,
                                     f"Sei stato dichiarato infortunato. Sono state rimosse {partecipazioni_rimosse[0]} iscrizioni a gare.")

            form.save()
            messages.success(request, f"Il tuo stato è stato aggiornato a '{atleta.get_stato_display()}'.")
        else:
            messages.error(request, "Errore durante l'aggiornamento del tuo stato.")

    return redirect('dashboard')


@login_required(login_url='/login/')
@user_passes_test(is_pres_regione)
def dashboard_pres_regione(request):
    presidente = get_object_or_404(PresidenteRegione, utente=request.user)

    # Filtra le gare in base al presidente di regione
    gare_future = Gara.objects.filter(data_fine__gte=now(), presidente_regione=presidente).order_by('data_inizio')
    gare_passate = Gara.objects.filter(data_fine__lt=now(), presidente_regione=presidente).order_by('data_fine')

    specialita_per_gara = {}
    iscritti_per_gara_futura = {}

    for gara in gare_future:
        specialita_per_gara[gara.pk] = GaraSpecialita.objects.filter(id_gara=gara)
        iscritti_per_gara_futura[gara.pk] = Partecipazione.objects.filter(id_gara=gara).select_related(
            'id_atleta__utente', 'id_specialita').order_by('id_atleta__utente__username')

    risultati_per_gara_passata = {}
    for gara in gare_passate:
        specialita_per_gara[gara.pk] = GaraSpecialita.objects.filter(id_gara=gara)
        risultati_per_gara_passata[gara.pk] = Partecipazione.objects.filter(id_gara=gara).select_related(
            'id_atleta__utente', 'id_specialita').order_by('id_specialita__nome')

    context = {
        'tipo_utente': 'PRES_REGIONE',
        'gare_future': gare_future,
        'gare_passate': gare_passate,
        'specialita_per_gara': specialita_per_gara,
        'risultati_per_gara_passata': risultati_per_gara_passata,
        'iscritti_per_gara_futura': iscritti_per_gara_futura,
    }
    return render(request, 'DBProject/dashboard_pres_regione.html', context)

@login_required(login_url='/login/')
@user_passes_test(is_allenatore)
def inserisci_risultato_view(request, id_partecipazione):
    allenatore = get_object_or_404(Allenatore, utente=request.user)
    partecipazione = get_object_or_404(Partecipazione, pk=id_partecipazione)

    # Verify that the coach belongs to the same team as the athlete
    if partecipazione.id_atleta.squadra != allenatore.squadra:
        messages.error(request, "Non hai i permessi per inserire i risultati per questo atleta.")
        return redirect('dashboard_allenatore')

    if request.method == 'POST':
        form = RisultatoForm(request.POST, instance=partecipazione)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Risultato per l'atleta '{partecipazione.id_atleta.utente.username}' inserito con successo!"
            )
            return redirect('dashboard_allenatore')
        else:
            messages.error(request, "Errore durante l'inserimento del risultato. Controlla i dati inseriti.")
    else:
        form = RisultatoForm(instance=partecipazione)

    context = {
        'form': form,
        'partecipazione': partecipazione,
        'tipo_utente': 'ALLENATORE',
    }
    return render(request, 'DBProject/inserisci_risultato.html', context)