from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.

class Stock(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100,null=True, blank=True)
    mse_url = models.URLField(max_length=500,null=True, blank=True)
    cloud_key = models.CharField(max_length=255,)
    last_modified = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    price = models.DecimalField(max_digits=10,decimal_places=2,null=True, blank=True)
    change = models.DecimalField(max_digits=4,decimal_places=2,null=True, blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['code']

class ApplicationUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='app_user')
    watchlist = models.ManyToManyField(Stock, related_name='watched_by', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email}'s Profile"

    def add_to_watchlist(self, stock):
        self.watchlist.add(stock)

    def remove_from_watchlist(self, stock):
        self.watchlist.remove(stock)

    def get_watchlist(self):
        return self.watchlist.all()

# Signal to create ApplicationUser when a new User is created
@receiver(post_save, sender=User)
def create_application_user(sender, instance, created, **kwargs):
    if created:
        ApplicationUser.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_application_user(sender, instance, **kwargs):
    instance.app_user.save()