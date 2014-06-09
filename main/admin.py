from django.contrib import admin
from buzz2tweet.main.models import TwitterAccount, GoogleProfile, SiteUser, Buzz, UserSettings, PushSubscription, Notification

class BuzzAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'published_on_twitter', 'failed_posting', 'retries', )
    
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('googleprofile', 'topic_url')
    

admin.site.register(TwitterAccount)
admin.site.register(GoogleProfile)
admin.site.register(SiteUser)
admin.site.register(Buzz, BuzzAdmin)
admin.site.register(UserSettings)
admin.site.register(PushSubscription, PushSubscriptionAdmin)
admin.site.register(Notification)


