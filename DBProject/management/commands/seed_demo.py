from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from DBProject.models import Utente


class Command(BaseCommand):
    help = "Carica i dati demo e imposta una password demo (solo con DEBUG=True)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="demo-password",
            help="Password assegnata a tutti gli utenti demo.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo e disabilitato con DEBUG=False.")
        if Utente.objects.exists():
            raise CommandError("Il database contiene gia utenti: comando annullato.")
        call_command("loaddata", "demo_data")
        Utente.objects.update(password=make_password(options["password"]))
        self.stdout.write(self.style.SUCCESS(
            f"Dati demo caricati: {Utente.objects.count()} utenti."
        ))
