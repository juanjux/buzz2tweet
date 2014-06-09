from django.conf.urls.defaults import *
from buzz2tweet.main.views import index, auth, twitterstep, settingsstep, twitter_return, docsstep, pubsub_callback
from django.views.generic.simple import direct_to_template

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', index, name='index'),
    #url(r'^auth/$', auth, name='auth'),
    #url('^return/$', twitter_return, name='return'),
    #url('^twitterstep/$', twitterstep, name='twitterstep'),
    #url('^settingsstep/(?P<userid>\w+)/$', settingsstep, name='settingsstep'),
    #url('^settingsstep/$', settingsstep, name='settingsstep'),
    #url('^docs/$', docsstep, name='docsstep'),
    #url('^pubsubcallback/(?P<gprofileid>\d+)/$', pubsub_callback, name='pubsubcallback'),
    #(r'commands/$', direct_to_template, {'template': 'commandhelp.html'}),
    #(r'faq/$', direct_to_template, {'template': 'faq.html'}),
    #(r'^admin/', include(admin.site.urls)),
)
