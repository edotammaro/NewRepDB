from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/allenatore/', views.dashboard_allenatore, name='dashboard_allenatore'),
    path('dashboard/pres-squadra/', views.dashboard_pres_squadra, name='dashboard_pres_squadra'),
    path('dashboard/pres-regione/', views.dashboard_pres_regione, name='dashboard_pres_regione'),
    path('pres-squadra/rimuovi-membro/<int:membro_id>/<str:tipo_membro>/', views.rimuovi_membro, name='rimuovi_membro'),
    path('pres-regione/crea-gara/', views.crea_gara_view, name='crea_gara'),
    path('pres-regione/rimuovi-gara/<int:gara_id>/', views.rimuovi_gara_view, name='rimuovi_gara'),
    path('dashboard/allenatore/iscrivi-atleti/<int:gara_specialita_id>/', views.iscrivi_atleti_gara, name='iscrivi_atleti_gara'),
    path('dashboard/allenatore/rimuovi-iscrizione/<int:partecipazione_id>/', views.rimuovi_iscrizione, name='rimuovi_iscrizione'),
    path('dashboard/atleta/aggiorna-stato/', views.aggiorna_stato_atleta, name='aggiorna_stato_atleta'),
    path('dashboard/allenatore/inserisci-risultato/<int:id_partecipazione>/', views.inserisci_risultato_view, name='inserisci_risultato'),
]
