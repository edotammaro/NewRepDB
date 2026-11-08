# AUDIT DI SICUREZZA - NewRepDB

Data audit: 03/11/2026  
Perimetro: Applicazione Django NewRepDB  
Modalità: Analisi statica del codice sorgente, configurazioni e cronologia git (Sola lettura)

---

## 1. Tabella di Sintesi delle Ipotesi

| # | Ipotesi | Esito | Severità | CWE |
|---|---|---|---|---|
| 1 | Escalation di ruolo in registrazione (ruolo scelto dall'utente senza controlli) | CONFERMATA | Critica | CWE-266 |
| 2 | IDOR / autorizzazione a livello di oggetto sulle view con ID | PARZIALE | Media | CWE-863 |
| 3 | Cancellazioni/modifiche di stato via GET o senza protezione CSRF | CONFERMATA | Media | CWE-352 |
| 4 | Lockout in FALLISMENTI_LOGIN (dizionario in memoria aggirabile / usabile per DoS) | CONFERMATA | Media | CWE-307, CWE-645, CWE-770 |
| 5 | Query raw/cursor.execute, \|safe, mark_safe, uso di export_dump.py | PARZIALE | Bassa | — |
| 6 | Settings: SECRET_KEY, DEBUG, ALLOWED_HOSTS, cookie, HSTS, X_FRAME_OPTIONS, validators | CONFERMATA | Media | CWE-321, CWE-489, CWE-614 |
| 7 | Vincoli "un solo presidente per regione/squadra" presenti solo nella logica Python | NON CONFERMATA | Bassa | CWE-754 |
| 8 | Storia git: SECRET_KEY e file db/dump committati | CONFERMATA | Bassa | CWE-540, CWE-321 |

---

## Registro dei problemi

Regola di severità: **Critica** = utente non autenticato ottiene il privilegio massimo o accesso a dati di terzi. **Alta** = privilegio ottenuto con un'azione della vittima o con un prerequisito. **Media** = indebolisce una difesa o causa perdita di dati. **Bassa/Info** = igiene, robustezza o documentazione.

| ID | Problema | Severità | CWE (verificata) | Stato |
|---|---|---|---|---|
| NRD-01 | Registrazione con ruolo a scelta e subentro in una squadra rimasta senza presidente | Critica | 266 | Risolto (`2fe3209` test, `f0bc0db` fix) |
| NRD-02 | Rimozioni via GET (`rimuovi_membro`, `rimuovi_iscrizione`, logout) | Media | 352 | Risolto (`ccbbcc6` test, `dc11c86` fix) |
| NRD-03 | `rimuovi_membro`: `delete()` a cascata e caso `squadra=None` | Media | 863 (parte autorizzazione), nessuna per la cascata | Risolto (`ccbbcc6`, `dc11c86`; riaggiunta membri `61103eb`, `380f099`) |
| NRD-04 | Lockout in RAM, mai azzerato alla scadenza, DoS su account altrui | Media | 307, 645, 770 | Risolto (`214fd78` test, `76f27b4` fix, `37e2b7e` test su X-Forwarded-For) |
| NRD-05 | Settings: SECRET_KEY hardcoded, DEBUG, hosts, cookie | Media | 321, 489, 614 | Parziale: SECRET_KEY, DEBUG e hosts da ambiente (`f40cea5`); cookie e HTTPS opt-in (`67c2d84` test, `37689bd` fix). Rotazione della chiave da fare al deploy |
| NRD-06 | Registrazione non atomica, utenti orfani | Bassa | 460 | Risolto (`2fe3209` test, `f0bc0db` fix) |
| NRD-07 | Repo: `.gitignore` spento, db/dump/.idea committati, SECRET_KEY nella storia | Bassa | 540, 321 | Parziale: `.gitignore` e file non più tracciati (`8e0fc06`, `e8408bb`). Storia git non riscritta |
| NRD-08 | Risultati accettati su gare non concluse (il README dice il contrario) | Bassa | 841 | Aperto |
| NRD-09 | Iscrizione senza regole su gara conclusa o sesso | Bassa | 841 | Aperto |
| NRD-10 | Errore 500 con `squadra=None` in `rimuovi_iscrizione` | Bassa | 476 | Risolto (`ccbbcc6` test, `dc11c86` fix) |
| NRD-11 | Codice morto e route duplicate; `cambia_stato_atleta_view` raggiungibile: cancellava le iscrizioni future e poi andava in errore (risolto) | Bassa | 561 | Risolto (`1ebf836`, `740b450`) |
| NRD-12 | Dipendenze con avvisi noti (Django 5.2.4, Pillow 11.3.0, sqlparse 0.5.3), `admin/` su percorso di default, requirements.txt in UTF-16 (convertito) | Media | 1395 (solo per le dipendenze; `admin/` e UTF-16 sono hardening, senza CWE) | Parziale: Django 5.2.18 (`fb920d6`), sqlparse 0.6.0 (`e1f05c6`), Pillow rimosso perché non usato (`d624b6b`), requirements in UTF-8 (`55c2222`). Restano django-axes 9, Django 6.x e `admin/` |
| NRD-13 | README con affermazioni assolute ("immune", lockout "efficace") | Info | nessuna | Aperto (README da riscrivere) |
| NRD-14 | Righe orfane nel database storico (chiavi esterne verso gare inesistenti) | Bassa | da verificare | Non verificato |
| NRD-15 | `squadra=None` non gestita: dashboard del presidente in errore 500; dashboard dell'allenatore con atleti, iscrizioni e risultati degli svincolati; scrittura di risultati di svincolati in `inserisci_risultato_view` perché `None != None` è falso | Media | da verificare | Risolto (`874f0af` test, `dac6765` fix, `193075c` test corretto) |

## 2. Dettaglio delle Ipotesi Verificate

### Ipotesi 1: Escalation di ruolo in registrazione
- **Esito**: CONFERMATA
- **Severità**: Critica
- **CWE**: CWE-266 (Incorrect Privilege Assignment)
- **Prova**:
  - `DBProject/forms.py:10-14`:
    ```python
    tipo = forms.ChoiceField(
        choices=Utente.TIPO_UTENTE_SCELTE,
        label="Scegli il tuo ruolo",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_tipo'})
    )
    ```
  - `DBProject/forms.py:45-58`:
    ```python
    if user.tipo == 'PRES_SQUADRA':
        nome_squadra = self.cleaned_data.get("nome_squadra")
        if nome_squadra:
            squadra_obj, created = Squadra.objects.get_or_create(nome=nome_squadra)
            PresidenteSquadra.objects.create(utente=user, squadra=squadra_obj)
        else:
            raise forms.ValidationError("Il Presidente di Squadra deve creare una squadra.")
    elif user.tipo == 'PRES_REGIONE':
        regione = self.cleaned_data.get("regione")
        if regione:
            PresidenteRegione.objects.create(utente=user, regione=regione)
        else:
            raise forms.ValidationError("Il Presidente di Regione deve avere una regione assegnata.")
    ```
  - `DBProject/views.py:35-46`:
    ```python
    def register_view(request):
        if request.method == "POST":
            form = RegistrazioneForm(request.POST)
            if form.is_valid():
                form.save()
    ```
- **Come si sfrutta (concettuale)**:
  Un utente anonimo invia una richiesta POST all'endpoint `/register/` specificando nel payload `tipo=PRES_REGIONE` (con un ID di regione non ancora assegnata) oppure `tipo=PRES_SQUADRA` (con un nome squadra). Il sistema crea immediatamente l'utente e il rispettivo profilo presidenziale senza alcuna approvazione da parte di un amministratore. Inoltre, nel caso di `PRES_SQUADRA`, l'uso di `get_or_create` a riga 48 consente a un utente di inserire il nome di una squadra già esistente ma rimasta senza presidente (es. per disattivazione o cancellazione del precedente titolare), acquisendone istantaneamente la presidenza e il controllo su tutti i relativi atleti e allenatori.
- **Fix proposto**:
  Rimuovere i ruoli apicali (`PRES_REGIONE`, `PRES_SQUADRA`) dalle scelte del form pubblico. La registrazione deve essere riservata ai ruoli base, delegando la nomina dei presidenti all'interfaccia amministrativa di Django con autorizzazione esplicita.

---

### Ipotesi 2: IDOR / autorizzazione a livello di oggetto sulle view con ID
- **Esito**: PARZIALE
- **Severità**: Media
- **CWE**: CWE-863 (Incorrect Authorization)
- **Prova**:
  L'analisi dettagliata di ogni view che riceve un ID nell'URL evidenzia quanto segue:
  1. `rimuovi_membro` (`DBProject/views.py:320, 324`):
     ```python
     if tipo_membro == 'atleta':
         membro = get_object_or_404(Atleta, pk=membro_id, squadra=squadra_utente)
     elif tipo_membro == 'allenatore':
         membro = get_object_or_404(Allenatore, pk=membro_id, squadra=squadra_utente)
     ```
     *Esito controllo*: VERIFICATO. Il membro deve appartenere a `squadra_utente`.  
     *Criticità*: se `request.user.presidentesquadra.squadra` è `None` (ammesso dal modello nullable), la query filtra `squadra=None`, consentendo l'eliminazione di membri svincolati.
  2. `rimuovi_gara_view` (`DBProject/views.py:370`):
     ```python
     gara = get_object_or_404(Gara, pk=gara_id)
     if gara.presidente_regione.utente != request.user:
         messages.error(request, "Non hai il permesso di rimuovere questa gara.")
         return redirect('dashboard')
     ```
     *Esito controllo*: VERIFICATO. La gara deve appartenere al presidente regionale richiedente.
  3. `rimuovi_iscrizione` (`DBProject/views.py:425`):
     ```python
     if iscrizione.id_atleta.squadra.allenatori.filter(utente=request.user).exists():
     ```
     *Esito controllo*: VERIFICATO. L'iscrizione può essere rimossa solo da un allenatore appartenente alla squadra dell'atleta.
  4. `inserisci_risultato_view` (`DBProject/views.py:504`):
     ```python
     if partecipazione.id_atleta.squadra != allenatore.squadra:
     ```
     *Esito controllo*: VERIFICATO per appartenenza squadra.  
     *Mancanza (discrepanza con la documentazione)*: `README.md:35-37` dichiara che la view verifica che la gara sia passata; nel codice Python tale controllo temporale (`data_fine < now()`) è del tutto assente, consentendo l'immissione di risultati per gare non ancora disputate.
  5. `iscrivi_atleti_gara` (`DBProject/views.py:384-385, 396` e `DBProject/forms.py:142-149`):
     ```python
     # DBProject/forms.py:142-148
     atleti_validi = Atleta.objects.filter(
         squadra=allenatore.squadra,
         stato='SANO'
     ).exclude(...)
     self.fields['atleti_selezionati'].queryset = atleti_validi

     # DBProject/views.py:396
     if atleta.squadra != allenatore.squadra:
         continue
     ```
     *Esito controllo*: VERIFICATO. Gli atleti selezionabili e iscrivibili sono rigorosamente vincolati lato server alla squadra dell'allenatore.  
     *Chiarimento sul modello dati e riclassificazione*: Nei modelli (`DBProject/models.py:44-49`) e in tutte le migrazioni storiche, il modello `Squadra` **non possiede alcun legame con `Regione`**. L'iscrizione di una squadra a gare di qualsiasi regione riflette l'assenza di vincoli territoriali nel dominio sportivo e non un IDOR. Le carenze sono limitate a **regole di business** (mancata verifica che la gara sia futura e assenza del campo `sesso` nel modello `Atleta`).
- **Come si sfrutta (concettuale)**:
  Tutte le view verificano l'appartenenza dell'oggetto all'utente o alla squadra di competenza. L'unico comportamento anomalo di autorizzazione si verifica in `rimuovi_membro` qualora un presidente di squadra non abbia una squadra associata (`squadra=None`): in tale scenario il filtro SQL ricerca `squadra_id IS NULL`, consentendo la cancellazione di atleti o allenatori registrati non ancora assegnati ad alcuna squadra.
- **Fix proposto**:
  In `rimuovi_membro`, verificare preventivamente che `squadra_utente` non sia `None`. In `inserisci_risultato_view`, aggiungere la convalida temporale:
  ```python
  if partecipazione.id_gara.data_fine and partecipazione.id_gara.data_fine >= now().date():
      messages.error(request, "Non è possibile inserire risultati per gare future o in corso.")
      return redirect('dashboard_allenatore')
  ```

---

### Ipotesi 3: Cancellazioni/modifiche di stato via GET o senza protezione CSRF
- **Esito**: CONFERMATA
- **Severità**: Media
- **CWE**: CWE-352 (Cross-Site Request Forgery)
- **Prova**:
  - `templates/DBProject/dashboard_allenatore.html:67-68`:
    ```html
    {{ partecipazione.id_atleta.utente.username }}
    <a href="{% url 'rimuovi_iscrizione' partecipazione.pk %}" class="btn btn-danger btn-sm" aria-label="Rimuovi Iscrizione">Rimuovi</a>
    ```
  - `DBProject/views.py:421-432`:
    ```python
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
    ```
  - `DBProject/views.py:316-330`:
    ```python
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
    ```
  - `templates/DBProject/base.html:27-28` e `DBProject/views.py:96-98`:
    ```html
    <a class="nav-link" href="{% url 'logout' %}">Logout</a>
    ```
    ```python
    @login_required(login_url='/login/')
    def logout_view(request):
        logout(request)
        return redirect('home')
    ```
- **Come si sfrutta (concettuale)**:
 Un attaccante induce un allenatore o presidente autenticato ad aprire un link (o una pagina che lo reindirizza) verso un URL come `/dashboard/allenatore/rimuovi-iscrizione/42/` o `/pres-squadra/rimuovi-membro/10/atleta/`. Con SameSite=Lax (default di Django) il browser invia il cookie di sessione nelle navigazioni top-level GET, quindi la view esegue `delete()` senza richiedere un POST con token CSRF. Le sottorisorse cross-site (es. immagini incorporate) non inviano il cookie e non sono un vettore valido con questa configurazione.
- **Fix proposto**:
  Applicare il decoratore `@require_POST` (o verificare `if request.method != 'POST': return HttpResponseNotAllowed(['POST'])`) a tutte le view di cancellazione (`rimuovi_iscrizione`, `rimuovi_membro`) e di logout (`logout_view`). Sostituire in `templates/DBProject/dashboard_allenatore.html` e `templates/DBProject/base.html` i tag `<a href>` con form HTML `<form method="post">` provvisti di `{% csrf_token %}`.

---

### Ipotesi 4: Lockout in FALLISMENTI_LOGIN (dizionario in memoria)
- **Esito**: CONFERMATA
- **Severità**: Media
- **CWE**: CWE-307 (Improper Restriction of Excessive Authentication Attempts), CWE-645 (Overly Restrictive Account Lockout Mechanism), CWE-770 (Allocation of Resources Without Limits or Throttling)
- **Prova**:
  - `DBProject/views.py:50-54`:
    ```python
    # Dizionario per tenere traccia dei tentativi di login falliti
    FALLISMENTI_LOGIN = {}
    # Numero massimo di tentativi prima del blocco
    MAX_TENTATIVI = 5
    # Tempo di blocco in secondi (es. 5 minuti)
    LOCKOUT_TIME = 5 * 60
    ```
  - `DBProject/views.py:64-70`:
    ```python
    now = time.time()
    if username and username in FALLISMENTI_LOGIN:
        tentativi_falliti, ultimo_tentativo = FALLISMENTI_LOGIN[username]
        if tentativi_falliti >= MAX_TENTATIVI and (now - ultimo_tentativo) < LOCKOUT_TIME:
            remaining_time = int(LOCKOUT_TIME - (now - ultimo_tentativo))
            messages.error(request, f"Troppi tentativi falliti per l'utente '{username}'. Riprova tra {remaining_time} secondi.")
            return render(request, 'DBProject/login.html', {'form': form})
    ```
  - `DBProject/views.py:75-77`:
    ```python
    login(request, user) # Resetta il contatore in caso di successo
    if username in FALLISMENTI_LOGIN:
        del FALLISMENTI_LOGIN[username]
    ```
  - `DBProject/views.py:84-89`:
    ```python
    if username:
        if username not in FALLISMENTI_LOGIN:
            FALLISMENTI_LOGIN[username] = [0, now]
        FALLISMENTI_LOGIN[username][0] += 1
        FALLISMENTI_LOGIN[username][1] = now
    ```
- **Come si sfrutta (concettuale)**:
  1. *Denial of Service su account mirati*: Il blocco è associato unicamente alla stringa `username` senza alcun controllo sull'indirizzo IP del client (`REMOTE_ADDR`). Un attaccante può inviare 5 tentativi di accesso falliti con password errata per un qualsiasi account bersaglio, bloccando l'accesso all'utente legittimo.
  2. *Mancato azzeramento del contatore alla scadenza del timeout*: Il contatore si azzera **esclusivamente a seguito di un login riuscito** (righe 76–77). Quando il timeout di 5 minuti (`LOCKOUT_TIME`) scade, il dizionario conserva inalterato il conteggio (`tentativi_falliti >= 5`). Se l'utente commette anche un solo ulteriore errore, il contatore viene incrementato a 6 aggiornando il timestamp (righe 87–88): al tentativo successivo il blocco si riattiva immediatamente per altri 5 minuti completi.
  3. *Inefficacia multi-worker e riavvio*: `FALLISMENTI_LOGIN` è memorizzato nella RAM del singolo worker WSGI; ogni riavvio azzera i blocchi, mentre in cluster multi-processo i contatori risultano disallineati.
  4. *Consumo incontrollato di memoria*: Il dizionario non applica alcuna politica di pulizia/TTL sui record scaduti, consentendo un attacco di saturazione memoria tramite invio di username inesistenti casuali.
- **Fix proposto**:
  Rimuovere completamente la struttura `FALLISMENTI_LOGIN`. Integrare una libreria standard come `django-axes` o un middleware di rate limiting basato su Redis/Django Cache, legando il vincolo alla coppia `(IP, username)` con finestre temporali scorrevoli e memorizzazione persistente condivisa tra tutti i worker.

---

### Ipotesi 5: Query raw/cursor.execute, |safe, mark_safe, uso di export_dump.py
- **Esito**: PARZIALE
- **Severità**: Bassa
- **CWE**: — (igiene del repository: `dump.sql` e `db.sqlite3` contengono dati demo, vedi Ipotesi 8)
- **Prova**:
  - `DBProject/` e `djangoDBProject/`: Nessuna occorrenza di `cursor.execute`, `.raw()` o query SQL manuali.
  - `templates/DBProject/`: Nessuna occorrenza del filtro di template `|safe`.
  - File Python applicativi: Nessuna occorrenza di `mark_safe` da `django.utils.safestring`.
  - `export_dump.py:1-16`:
    ```python
    import sqlite3

    # Nome del file del tuo database Django
    db_filename = "db.sqlite3"
    dump_filename = "dump.sql"

    # Connessione al database
    conn = sqlite3.connect(db_filename)

    # Creazione del dump
    with open(dump_filename, "w", encoding="utf-8") as f:
        for line in conn.iterdump():
            f.write("%s\n" % line)

    conn.close()
    ```
  - `dump.sql:1-473`: File generato da `export_dump.py` e presente nella radice del progetto, contenente 473 righe di dump SQL con definizioni di tabelle e dati.
- **Come si sfrutta (concettuale)**:
  Non sono riscontrabili criticità di SQL Injection (l'ORM Django è usato ovunque correttamente) né XSS derivanti da escaping disabilitato. Tuttavia, l'esecuzione di `export_dump.py` ha riversato l'intero database in chiaro nel file statico `dump.sql`. Trovandosi nella radice del repository, chiunque abbia accesso in lettura al repository o alla cartella può estrarre credenziali, hash e dati anagrafici.
- **Fix proposto**:
  Rimuovere `export_dump.py` dal progetto o limitarne l'uso a script di backup protetti fuori dal web root. Eliminare `dump.sql` e aggiungerlo a `.gitignore`.

---

### Ipotesi 6: Settings: SECRET_KEY, DEBUG, ALLOWED_HOSTS, cookie, HSTS, X_FRAME_OPTIONS, validators
- **Esito**: CONFERMATA
- **Severità**: Media
- **CWE**: CWE-321 (Use of Hard-coded Cryptographic Key), CWE-489 (Active Debug Code), CWE-614 (Sensitive Cookie in HTTPS Session Without 'Secure' Attribute)
- **Prova**:
  - `djangoDBProject/settings.py:24`:
    ```python
    SECRET_KEY = "[redatto]"
    ```
  - `djangoDBProject/settings.py:27`:
    ```python
    DEBUG = True
    ```
  - `djangoDBProject/settings.py:29`:
    ```python
    ALLOWED_HOSTS = []
    ```
  - `djangoDBProject/settings.py:47-55`:
    ```python
    MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
    ```
  - Assenza nei settings delle direttive per HTTPS e cookie:
    - `SESSION_COOKIE_SECURE` (non impostato, default `False`)
    - `CSRF_COOKIE_SECURE` (non impostato, default `False`)
    - `SESSION_COOKIE_SAMESITE` (non impostato, default `Lax`)
    - `CSRF_COOKIE_SAMESITE` (non impostato, default `Lax`)
    - `SECURE_HSTS_SECONDS` (non impostato)
    - `SECURE_SSL_REDIRECT` (non impostato, default `False`)
  - `djangoDBProject/settings.py:92-105`:
    `AUTH_PASSWORD_VALIDATORS` è regolarmente configurato con i 4 validatori ufficiali di Django.
  - `X_FRAME_OPTIONS`: gestito dal middleware `XFrameOptionsMiddleware` (presente a riga 54, default `DENY` in Django 5.x).
- **Come si sfrutta (concettuale)**:
  Con `DEBUG = True`, un'eccezione non gestita mostra la pagina di debug con frammenti di codice, percorsi, variabili locali e dati della richiesta. Django oscura nella pagina i valori dei settings con nomi come SECRET o KEY, quindi la chiave non vi compare. La `SECRET_KEY` hardcoded e presente nella storia git resta comunque un rischio: serve a firmare messaggi, token di reset password e cookie firmati. Con il backend di sessione di default (sessioni nel DB, cookie con ID casuale) la sola chiave non permette di forgiare sessioni. L'assenza di `Secure` sui cookie permette l'intercettazione dei token su reti non cifrate.
- **Fix proposto**:
  Esternalizzare `SECRET_KEY`, `DEBUG` e `ALLOWED_HOSTS` tramite variabili d'ambiente (es. file `.env` con `django-environ`). Impostare per la produzione:
 
 ```python
import os

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h]

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # valutare un valore basso all'inizio
```
 

### Ipotesi 7: Vincoli "un solo presidente per regione/squadra" solo in Python o anche nel DB
- **Esito**: NON CONFERMATA (l'ipotesi sul database non regge; resta l'errore 500 sul duplicato, vedi dettaglio)
- **Severità**: Bassa
- **CWE**: CWE-754 (Improper Check for Unusual or Exceptional Conditions)
- **Prova**:
  - `DBProject/models.py:59-64`:
    ```python
    class PresidenteRegione(models.Model):
        utente = models.OneToOneField(Utente, on_delete=models.CASCADE, primary_key=True)
        regione = models.OneToOneField(Regione, on_delete=models.CASCADE)
    ```
  - `DBProject/models.py:99-107`:
    ```python
    class PresidenteSquadra(models.Model):
        utente = models.OneToOneField('Utente', on_delete=models.CASCADE)
        squadra = models.OneToOneField(
            'Squadra',
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            related_name='presidente'
        )
    ```
  - `DBProject/migrations/0001_initial.py:247, 300`:
    Sia in `PresidenteSquadra` sia in `PresidenteRegione`, i campi `squadra` e `regione` sono generati come `models.OneToOneField`.
  - `dump.sql:220, 227`:
    ```sql
    CREATE TABLE "DBProject_presidenteregione" (..., "regione_id" bigint NOT NULL UNIQUE REFERENCES "DBProject_regione" ("id")...);
    CREATE TABLE "DBProject_presidentesquadra" (..., "squadra_id" bigint NULL UNIQUE REFERENCES "DBProject_squadra" ("id")...);
    ```
- **Come si sfrutta (concettuale)**:
  L'ipotesi di assenza di vincoli a livello DB non è confermata: il database applica regolarmente il vincolo `UNIQUE` sulle chiavi esterne grazie al costrutto `OneToOneField`. Non è possibile associare più presidenti alla medesima squadra o regione nel DB.
  Tuttavia, poiché in `DBProject/forms.py:45-58` non viene effettuata una validazione applicativa preventiva nel metodo `clean()`, l'inserimento di un duplicato scatena un'eccezione non gestita `django.db.utils.IntegrityError`, provocando un crash applicativo (HTTP 500) invece di un messaggio d'errore leggibile.
- **Fix proposto**:
  Aggiungere controlli di validazione nel form di registrazione (`DBProject/forms.py`):
  ```python
  def clean_regione(self):
      regione = self.cleaned_data.get('regione')
      if self.cleaned_data.get('tipo') == 'PRES_REGIONE':
          if not regione:
              raise forms.ValidationError("Seleziona una regione.")
          if PresidenteRegione.objects.filter(regione=regione).exists():
              raise forms.ValidationError("La regione selezionata ha già un presidente assegnato.")
      return regione
  ```

---

### Ipotesi 8: Storia git: SECRET_KEY o dati reali in commit passati
- **Esito**: CONFERMATA
- **Severità**: Bassa
- **CWE**: CWE-540 (Inclusion of Sensitive Information in Source Code), CWE-321 (Use of Hard-coded Cryptographic Key)
- **Prova**:
  - `commit 01355ed53e69006761599a53569a1b84d847f9d7` ("Initial commit del progetto Django"):
    File `djangoDBProject/settings.py` introdotto con la chiave `SECRET_KEY = "[redatto]"`.
  - `commit 5463ee5bf7b3c9ffb77637b6f5cda97afefa9895` ("dump database"):
    Aggiunto il file `dump.sql` contenente 473 righe con dump completo di tabelle e dati.
  - - Metadati git: 3 coppie nome/email distinte nei commit (due con nome autore `edotammaro`, di cui una è la noreply di GitHub, e una con nome autore `gts`). Indirizzi omessi dal documento.
  - Censimento di tutti i database SQLite e dump presenti nella storia Git (tabella riassuntiva basata esclusivamente su conteggi):

| Database / File | Commit / Riferimento Git | Dimensione (byte) | Totale Utenti | Superutenti | Domini Email (Conteggio) |
|---|---|---|---|---|---|
| `db.sqlite3` | `commit becf2b9` (blob `1000f6f`) | 266.240 | 6 | 0 | `gmail.com`: 4<br>`gmai.com`: 2 |
| `db.sqlite3` | `commit 9dde3c7` (blob `27271a9`) | 282.624 | 45 | 0 | `gmail.com`: 45 |
| `db.sqlite3` | `commit d6973ef` (blob `1fc0f91`) | 282.624 | 45 | 0 | `gmail.com`: 45 |
| `db.sqlite3` | `commit ed96fd5` (blob `afca69d`) | 282.624 | 45 | 0 | `gmail.com`: 45 |
| `db.sqlite3` | Working tree (attuale) | 282.624 | 45 | 0 | `gmail.com`: 45 |
| `dump.sql` | `commit 5463ee5` e working tree | 49.976 | 45 | 0 | `gmail.com`: 45 |
| `identifier.sqlite` | Tutti i commit (`badf82d`, `3475b34`, `becf2b9`) | 0 | 0 | 0 | Nessuno |

- **Analisi della natura degli account archiviati nel database**:
  L'analisi sistematica del database dimostra che tutti i 45 account utente presenti in `dump.sql` e nei database storici sono **account demo e seed fittizi**:
  - In 44 casi su 45, la parte locale dell'email coincide con il nome del ruolo (`PresidenteCalabria`, `AtletaM1Squadra1`, ecc.);
  - In 1 caso su 45, l'email contiene il nome della regione per esteso (`presidente.friuliveneziagiulia`);
  - In 0 casi sono presenti email slegate dal ruolo.
  - I 6 utenti presenti nella versione iniziale (`commit becf2b9`) avevano anch'essi email corrispondenti al proprio username di test e **nessuno dei 6 compare tra i 45 utenti delle versioni successive** (sono stati interamente sostituiti). Non è presente alcuna email personale di atleti o utenti reali nel database.
- **Come si sfrutta (concettuale)**:
  Chiunque cloni o abbia accesso al repository può estrarre tramite comandi git i file `dump.sql` e le versioni storiche di `db.sqlite3`. Da questi è possibile prelevare gli hash delle password per condurre attacchi di cracking offline, oltre a ricavare l'elenco degli utenti e la `SECRET_KEY`.
- **Fix proposto**:
  1. Rigenerare immediatamente la `SECRET_KEY` in produzione e forzare il reset delle password per tutti gli utenti presenti nel database.
  2. Rimuovere `db.sqlite3` e `dump.sql` dal repository.
  3. Decisione: la cronologia git non è stata riscritta. I dati nei database storici sono sintetici (vedi l'analisi sopra) e la mitigazione scelta è la rotazione della `SECRET_KEY`; `git-filter-repo` resterebbe l'opzione se in futuro si volessero eliminare i file dalla storia.
  4. Configurare e forzare `.gitignore` prima di nuovi commit.

---

## 3. Problemi Trovati che NON Erano nelle Ipotesi

1. **Mancanza di transazione atomica in `RegistrazioneForm.save()` e creazione di utenti orfani**
   - **File e riga**: `DBProject/forms.py:43-57`
   - **Estratto**:
     ```python
     if commit:
         user.save()

         if user.tipo == 'PRES_SQUADRA':
             nome_squadra = self.cleaned_data.get("nome_squadra")
             if nome_squadra:
                 squadra_obj, created = Squadra.objects.get_or_create(nome=nome_squadra)
                 PresidenteSquadra.objects.create(utente=user, squadra=squadra_obj)
     ```
   - **Descrizione**: Il salvataggio dell'utente `user.save()` (riga 43) viene eseguito nel database prima della creazione del profilo collegato (`PresidenteSquadra` o `PresidenteRegione`), senza essere racchiuso in un blocco `transaction.atomic()`. Se la successiva chiamata `.create()` solleva un'eccezione (es. `IntegrityError` perché la squadra o la regione sono già occupate), l'operazione fallisce con errore HTTP 500 ma l'istanza `Utente` rimane orfana nel database. Lo username risulta quindi occupato e non più registrabile, e a ogni successivo login dell'utente la dashboard solleva un errore 404 per assenza del profilo collegato.

2. **File `.gitignore` interamente disabilitato**
   - **File e riga**: `.gitignore:1-14`
   - **Estratto**:
     ```gitignore
     # Byte-compiled / optimized / DLL files
     #__pycache__/
     #*.py[cod]

     # Databases
     #*.sqlite3

     # Django-specific files
     #/media/
     #/static/

     # IDE files
     #.idea/
     #.vscode/
     ```
   - **Descrizione**: Tutte le direttive nel file `.gitignore` sono precedute da `#` (commentate). Di conseguenza, Git non ignora alcun file, portando al commit accidentale di cartelle di sistema IDE (`.idea/`), file compilati (`__pycache__/`) e database binari (`db.sqlite3`).

3. **Credenziali predefinite esposte in chiaro nel `README.md`**
   - **File e riga**: `README.md:19-21, 26-28, 44-46, 52-55`
   - **Estratto**:
     ```markdown
     Credenziali per testare: 
     - Username: PresidenteSquadra1, PresidenteSquadra2...
     - Password: [redatto]
     ```
   - **Descrizione**: Il documento di istruzioni espone pubblicamente la password comune predefinita per tutti gli account di test e ruoli amministrativi. Se il database committato viene distribuito in staging o produzione senza bonifica, gli account risultano immediatamente compromessi.

4. **Cancellazione distruttiva a cascata su disassociazione atleti in `rimuovi_membro`**
   - **File e riga**: `DBProject/views.py:320-322`, `DBProject/models.py:157`
   - **Estratto**:
     ```python
     membro = get_object_or_404(Atleta, pk=membro_id, squadra=squadra_utente)
     membro.delete()
     ```
     e in `Partecipazione`:
     ```python
     id_atleta = models.ForeignKey(Atleta, on_delete=models.CASCADE)
     ```
   - **Descrizione**: Quando un presidente di squadra rimuove un atleta dalla squadra, il codice esegue `membro.delete()`, cancellando l'intera istanza del profilo atleta anziché disassociare la squadra (`atleta.squadra = None`). A causa del vincolo `CASCADE` su `Partecipazione.id_atleta`, vengono irrimediabilmente distrutte tutte le iscrizioni, i tempi e lo storico dei risultati sportivi conseguiti dall'atleta in tutta la sua carriera.

5. **NameError e route inesistente in `cambia_stato_atleta_view`**
   - **File e riga**: `DBProject/views.py:543, 547, 554` e `DBProject/urls.py:21`
   - **Estratto**:
     ```python
     # DBProject/urls.py:21
     path('dashboard/atleta/cambia-stato/', views.cambia_stato_atleta_view, name='cambia_stato_atleta'),

     # DBProject/views.py:543, 547
     atleta.stato = StatoAtleta.INFORTUNATO
     ...
     atleta.stato = StatoAtleta.ATTIVO
     ...
     return redirect('dashboard_atleta')
     ```
   - **Descrizione**: La view è attivamente registrata in `urls.py:21`, ma il codice fa riferimento all'identificatore `StatoAtleta` che non è importato né definito in `views.py`. L'invocazione della view solleva un'eccezione irreversibile `NameError`. Inoltre, il redirect richiama il nome `'dashboard_atleta'`, che non esiste in `DBProject/urls.py`, provocando un `NoReverseMatch`.
   - **Stato**: risolto nel commit `1ebf836` (view e route rimosse). Nel ramo "infortunato" le iscrizioni future venivano cancellate (righe 539-542) prima dell'errore `NameError` (riga 543); senza `ATOMIC_REQUESTS` nei settings la richiesta restituiva un 500 dopo aver già modificato i dati. I numeri di riga si riferiscono al tag `v0-original`.

6. **Duplicazione asimmetrica della funzione `aggiorna_stato_atleta` e ridondanza in `urls.py`**
   - **File e riga**: `DBProject/views.py:167-186` e `DBProject/views.py:437-461`; `DBProject/urls.py:18-19`
   - **Estratto**:
     Prima definizione (righe 174-177):
     ```python
     Partecipazione.objects.filter(
         id_atleta=atleta,
         id_gara__data_fine__gte=now()
     ).delete()
     ```
     Seconda definizione (righe 448-451):
     ```python
     Partecipazione.objects.filter(
         id_atleta=atleta,
         id_gara__data_inizio__gte=now()
     ).delete()
     ```
     E in `urls.py`:
     ```python
     path('dashboard/atleta/aggiorna-stato/', views.aggiorna_stato_atleta, name='aggiorna_stato_atleta'),
     path('dashboard/atleta/aggiorna-stato/', views.aggiorna_stato_atleta, name='aggiorna_stato_atleta'),
     ```
   - **Descrizione**: La funzione `aggiorna_stato_atleta` è definita due volte nello stesso modulo `views.py`. All'avvio dell'applicazione la seconda definizione (righe 437-461) sovrascrive completamente la prima nel namespace. La logica della seconda definizione utilizza `data_inizio__gte=now()` invece di `data_fine__gte=now()`, introducendo un disallineamento funzionale se una gara è in corso su più giorni. Inoltre, in `urls.py` la stessa identica route è registrata due volte consecutive.
   - **Stato**: risolto nel commit `1ebf836`: rimosse la definizione morta (righe 167-186) e la route duplicata; la route `dashboard_view`, irraggiungibile perché coperta da `dashboard/`, è stata tolta e i redirect usano `dashboard`. Resta aperta la scelta funzionale tra `data_inizio` e `data_fine` nella versione attiva.

7. **Esposizione della route amministrativa predefinita `admin/`**
   - **File e riga**: `djangoDBProject/urls.py:21`
   - **Estratto**:
     ```python
     urlpatterns = [
         path('admin/', admin.site.urls),
         path('', include('DBProject.urls')),
     ]
     ```
   - **Descrizione**: L'interfaccia di amministrazione di Django è esposta sul path convenzionale `/admin/`. In ambienti di produzione è consigliabile modificare il percorso o limitarne l'accesso a livello di reverse proxy per prevenire attacchi di forza bruta e scansioni automatiche.

8. **Presenza di dati personali e particolari nelle tabelle del database**
   - **File e riga**: `DBProject/models.py:7-34, 66-83` e `dump.sql:11, 262`
   - **Descrizione**: Dall'analisi dello schema del database emergono le seguenti colonne a rischio dati personali:
     - Tabella `DBProject_atleta`: colonna `stato` (tratta dati sullo stato di salute 'SANO' / 'INFORTUNATO', classificabili come dati personali particolari/sensibili ex art. 9 GDPR).
     - Tabella `DBProject_utente`: colonne `email`, `username`, `first_name`, `last_name` (dati personali diretti), nonché `password` (hash di credenziali personali) e `last_login` (metadati di tracciamento attività).

9. **Codifica UTF-16LE del file `requirements.txt`**
   - **File**: `requirements.txt`
   - **Descrizione**: Il file delle dipendenze è salvato con codifica UTF-16LE con byte-order mark (BOM) anziché con la codifica standard UTF-8 / ASCII. Ciò può causare errori di parsing in pipeline CI/CD o ambienti di build Linux automatizzati.
   - **Stato**: convertito in UTF-8 senza BOM nel commit `55c2222`. `pip-audit` leggeva comunque il file grazie al BOM, quindi il problema può riguardare altri strumenti (CI, ricerche di testo, bot di aggiornamento).

10. **File residuo da reflog Git committato nella root**
    - **File e riga**: `et --hard ef7d4bb:1-16`
    - **Descrizione**: File generato da un refuso di digitazione di un comando git (`git reset --hard ef7d4bb`), contenente output di reflog con hash di commit e nomi di branch interni, committato nella radice del progetto.

11. **Mancanza di validazione del sesso nell'iscrizione degli atleti**
    - **File e riga**: `DBProject/models.py:66-83`, `DBProject/forms.py:142-150`, `DBProject/views.py:383-416`
    - **Descrizione**: Il modello `GaraSpecialita` specifica l'attributo `sesso` (`M`/`F`), ma il modello `Atleta` non possiede alcun campo relativo al genere. Di conseguenza, il form e la view consentono l'iscrizione di qualsiasi atleta a gare di genere differente senza alcun vincolo di integrità.

12. **Possibile eccezione `AttributeError` in `rimuovi_iscrizione`**
    - **File e riga**: `DBProject/views.py:425`
    - **Estratto**:
     ```python
     if iscrizione.id_atleta.squadra.allenatori.filter(utente=request.user).exists():
     ```
    - **Descrizione**: Poiché `Atleta.squadra` ammette valori `NULL` (`null=True`), se un'iscrizione appartiene a un atleta la cui squadra è stata annullata, l'accesso a `iscrizione.id_atleta.squadra.allenatori` scatena un'eccezione non gestita `AttributeError: 'NoneType' object has no attribute 'allenatori'` con errore HTTP 500.

---

13. **Righe orfane nel database storico**
   - **File**: `db.sqlite3` (tracciato fino al commit `e8408bb`)
   - **Descrizione**: `PRAGMA foreign_key_check` ha trovato 3 righe con chiave esterna verso gare inesistenti: la partecipazione 44 (gara 19) e le gara-specialità 29 (gara 19) e 60 (gara 27). Le righe orfane fanno fallire `loaddata` con `IntegrityError`. La causa non è verificata: un'ipotesi è che le gare siano state cancellate senza la cascata applicativa (per esempio da un client SQL), ma non è stato dimostrato. Da controllare se `rimuovi_gara_view` può lasciare righe orfane: in tal caso il problema è nel codice e va collegato a NRD-03.
   - **Stato**: le 3 righe sono escluse dalla fixture demo (commit `2d922b4`); il database originale non è stato modificato (copia di sicurezza fuori dal repository).

## 4. Cose che Ho Controllato e Sono a Posto

1. **Middleware CSRF globale attivo**
   - **Prova**: `djangoDBProject/settings.py:51`
   - **Dettaglio**: `django.middleware.csrf.CsrfViewMiddleware` è regolarmente posizionato nella lista `MIDDLEWARE`. Tutte le richieste POST standard sono soggette alla validazione del token CSRF.

2. **Inclusione del token CSRF nei form POST dei template**
   - **Prova**:
     - `templates/DBProject/crea_gara.html:6` (`{% csrf_token %}`)
     - `templates/DBProject/dashboard.html:25` (`{% csrf_token %}`)
     - `templates/DBProject/dashboard_allenatore.html:57` (`{% csrf_token %}`)
     - `templates/DBProject/dashboard_atleta.html:15` (`{% csrf_token %}`)
     - `templates/DBProject/dashboard_pres_regione.html:26` (`{% csrf_token %}`)
     - `templates/DBProject/dashboard_pres_squadra.html:22, 44, 59, 71` (`{% csrf_token %}`)
     - `templates/DBProject/inserisci_risultato.html:23` (`{% csrf_token %}`)
     - `templates/DBProject/login.html:21` (`{% csrf_token %}`)
     - `templates/DBProject/register.html:13` (`{% csrf_token %}`)
   - **Dettaglio**: Tutti i form HTML che effettuano invii POST includono correttamente il tag `{% csrf_token %}`.

3. **Protezione Clickjacking (X-Frame-Options)**
   - **Prova**: `djangoDBProject/settings.py:54`
   - **Dettaglio**: Il middleware `django.middleware.clickjacking.XFrameOptionsMiddleware` è attivo. In assenza di override espliciti, Django imposta automaticamente l'header `X-Frame-Options: DENY`, proteggendo l'applicazione dall'inclusione in frame o iframe esterni.

4. **Assenza di SQL Injection via Query Raw / Concatenazione**
   - **Prova**: Verifica statica su tutti i file `.py` in `DBProject/` e `djangoDBProject/`.
   - **Dettaglio**: Non vi è alcuna occorrenza di `cursor.execute()`, chiamate `.raw()` o interpolazioni di stringhe all'interno di comandi SQL. Ogni operazione sul database viene mediata dalle query parametrizzate dell'ORM di Django (`filter`, `get`, `create`, `select_related`, `exclude`).

5. **Assenza di XSS provocato da `|safe` o `mark_safe`**
   - **Prova**: Verifica statica su tutti i file `.html` in `templates/DBProject/` e `.py` in `DBProject/`.
   - **Dettaglio**: Nessun template utilizza il filtro `|safe` per disabilitare l'auto-escaping. Nessun codice Python fa ricorso a `mark_safe` o `SafeString`. L'escaping automatico di Django rimane attivo su tutte le variabili stampate nei template.

6. **Password Hashing robusto (PBKDF2)**
   - **Prova**: `dump.sql:263-277`
   - **Dettaglio**: Le password degli utenti non sono salvate in chiaro ma con l'algoritmo standard PBKDF2 con salt casuale e fattore di costo a 1.000.000 di iterazioni (standard di sicurezza moderno di Django 5.x).

7. **Configurazione dei validatori password**
   - **Prova**: `djangoDBProject/settings.py:92-105`
   - **Dettaglio**: La lista `AUTH_PASSWORD_VALIDATORS` include tutti e quattro i validatori standard Django (`UserAttributeSimilarityValidator`, `MinimumLengthValidator`, `CommonPasswordValidator`, `NumericPasswordValidator`), attivi durante la validazione di `UserCreationForm`.

8. **Verifica di autorizzazione a livello di oggetto sulle operazioni critiche**
   - **Prova**:
     - `DBProject/views.py:370`: la rimozione di una gara verifica rigorosamente che `gara.presidente_regione.utente == request.user`.
     - `DBProject/views.py:504`: l'inserimento o la modifica dei risultati di gara verifica che `partecipazione.id_atleta.squadra == allenatore.squadra`.
     - `DBProject/views.py:320, 324`: la rimozione di un membro verifica che il membro appartenga a `squadra_utente`.
     - `DBProject/views.py:396` e `DBProject/forms.py:142-149`: l'iscrizione atleti a gara verifica che gli atleti appartengano alla squadra dell'allenatore.
   - **Dettaglio**: Tutte le view sensibili implementano verifiche di appartenenza alla squadra o alla giurisdizione dell'utente autenticato.

9. **Gestione controllata degli utenti registrati privi di profilo squadra**
   - **Prova**: `DBProject/views.py:104-152`
   - **Dettaglio**: Un utente autenticato con `tipo='ATLETA'` a cui non è stata ancora associata un'istanza `Atleta` non genera un errore HTTP 500. `dashboard_view` intercetta l'eccezione `Atleta.DoesNotExist` (riga 149), notificando l'utente con un messaggio informativo e consentendo l'accesso alla dashboard di base (HTTP 200).

## 5. Limiti dell'analisi

- Solo analisi statica del codice e della storia git: nessun test dinamico, nessun exploit eseguito.
- Dipendenze scansionate con `pip-audit` il 05/11/2026: avvisi noti su Django 5.2.4, Pillow 11.3.0 e sqlparse 0.5.3 (vedi NRD-12). La sfruttabilità nell'app non è stata valutata e il numero di avvisi distinti non è stato contato.
- I dati nei database storici sono stati valutati solo tramite conteggi e struttura.
- Severità e CWE sono valutazioni tentative. Le CWE sono state poi verificate su cwe.mitre.org il 07/11/2026 (vedi nota sotto); le severità restano tentative.
- Verifica del 07/11/2026 su cwe.mitre.org: tutte le CWE del registro esistono; 269, 755 e 798 sono state sostituite perché sconsigliate o ammesse solo in casi limitati. Stato di mapping: Allowed per 266, 460, 321, 307, 352, 489, 614, 540, 561, 645, 770, 476, 841; Allowed-with-Review (uso limitato, da motivare) per 863, 754, 1395. Adattamenti deboli: 841 su NRD-08/09 (la CWE descrive una sequenza di azioni in una sessione, qui è una precondizione sullo stato della gara); 540 su NRD-07 vale per la SECRET_KEY nel codice, non per db e dump (dati, non codice sorgente); 561 su NRD-11 vale solo per le parti irraggiungibili, non per cambia_stato_atleta_view, che era raggiungibile e difettosa.
- Aggiornamento dello stato dei fix dell'08/11/2026: la colonna Stato del registro si basa sui messaggi dei commit e sui test. Lo stato di NRD-07 non è stato riverificato sul repo.
- NRD-15: severità tentativa, CWE da verificare su cwe.mitre.org. La prova del test rosso sulla scrittura dei risultati mostra un redirect 302 sul codice senza fix: da solo non prova la scrittura nel database, che si deduce dal codice (`None != None`) e dal test di controllo positivo.
- NRD-04: i test mostrano che oggi `X-Forwarded-For` è ignorato (django-axes usa `REMOTE_ADDR` se django-ipware non è installato). Non è stato verificato che diventino rossi installando django-ipware.
- NRD-05: il test HTTPS verifica che `check --deploy` sia pulito con `DJANGO_HTTPS=1`, non l'emissione reale dei cookie `Secure` né il redirect. `security.W005` e `security.W021` sono silenziati senza aver verificato che comparirebbero. `SECURE_PROXY_SSL_HEADER` non è impostato: dietro un proxy che termina TLS il redirect andrebbe in loop. La rotazione della `SECRET_KEY` è operativa e va fatta al deploy.
- NRD-12: gli avvisi elencati da PyPI sono associati alla versione, non a un'analisi dell'uso nel codice. Pillow è stato rimosso perché non risulta usato (cercati `.py`, `.html`, `.txt`, `.md`; nessun pacchetto installato lo richiede); altri formati di file non sono stati cercati. django-axes 9.0.0 non è stato adottato perché uscita da meno di 14 giorni.
- NRD-14: il database locale è stato ricreato vuoto; le righe orfane del database storico non sono state riverificate.
