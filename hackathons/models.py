# TEMPORAIRE — Modèle Hackathon minimal, stub pour développement local.
# La vraie implémentation est dans la PR de la coéquipière.
# Ne pas inclure dans la PR du module sponsors.

from django.db import models


class Hackathon(models.Model):
    """
    TEMPORAIRE : modèle stub utilisé uniquement pour permettre les migrations
    de l'app sponsors en local. La vraie app hackathons sera fournie par une coéquipière.
    """

    name = models.CharField(max_length=255, verbose_name="Nom")
    theme = models.CharField(max_length=255, blank=True, verbose_name="Thème")
    start_date = models.DateField(null=True, blank=True, verbose_name="Date de début")
    end_date = models.DateField(null=True, blank=True, verbose_name="Date de fin")

    class Meta:
        verbose_name = "Hackathon [TEMPORAIRE]"
        verbose_name_plural = "Hackathons [TEMPORAIRE]"
        ordering = ["-start_date"]

    def __str__(self):
        return self.name
