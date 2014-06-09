from datetime import datetime, timedelta
from pprint import pprint
from django.db import models
from django import forms
import feedparser

import logging
import logging.handlers
from buzz2tweet import settings
class BuzzFeedParsingException(Exception): pass


"""
# XXX TEMPORAL

LOGGER = None

def get_listener_logger():
    global LOGGER
    
    if not LOGGER:
        LOGGER = logging.getLogger('listener')
        LOGGER.setLevel(settings.LOGLEVEL)
        handler = logging.handlers.RotatingFileHandler(settings.LOG_LISTENER, maxBytes=10485760, backupCount=10)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        LOGGER.addHandler(handler)
    
    return LOGGER
"""

class PushSubscription(models.Model):
    
    created_at  = models.DateTimeField('created', auto_now_add=True)
    
    # Put to True when the Push server confirmation request is replied
    confirmed   = models.BooleanField('confirmed', default=False)
    
    # When the user unsubscribed this is put to True, so we know we have to reply 200 to
    # unsubscribe confirmations from the push server (to avoid man-in-the-middle attacks):
    userdeleted = models.BooleanField('userdeleted', default=False)
    
    # Date of the last renewal to the renewal cron knows if a renewal request must be issued
    renewed_at  = models.DateTimeField('renewed')
    
    # See above, renewed_at + lease_time - somevalue = cron must renew
    lease_time  = models.IntegerField('leasetime', default=0)
    topic_url   = models.URLField('topic')
    
    # Trought a OneToOne would be more logical I dont want cascading deletions of this field, because
    # the GoogleProfile is deleted when the user issued an unsubscribe request but this should be only
    # deleted after the unsubscription from the push server is confirmed (when the GoogleProfile is deleted
    # the field delete above is set to True.)
    googleprofile = models.ForeignKey('GoogleProfile', blank=True, null=True)
    
    def __unicode__(self):
        return self.topic_url
 
 
class Notification(models.Model):
    created_at = models.DateField('created', auto_now_add=True)
    text = models.TextField('text')
    googleprofile = models.ForeignKey('GoogleProfile')
    
    def __unicode__(self):
        return self.googleprofile.username + u'|' + self.text


class TwitterAccount(models.Model):
    """Twitter Account data (with encypted passwd)"""

    created_at  = models.DateTimeField('created', auto_now_add=True)
    modified_at = models.DateTimeField('modified', auto_now=True)
    name        = models.CharField('name', max_length=128, unique=True)
    token       = models.CharField('token', max_length=128, blank=True, null=True)
    siteuser    = models.OneToOneField('SiteUser')

    def __unicode__(self):
            return self.name
 
           
class GoogleProfile(models.Model):
    created_at      = models.DateTimeField('created', auto_now_add=True)
    modified_at     = models.DateTimeField('modified', auto_now=True)
    lastbuffread_at = models.DateTimeField('lastbuffread_at', blank=True, null=True)
    firsttime       = models.BooleanField('firsttime', default=True)
    retries         = models.IntegerField('retries', default=0)
    siteuser        = models.OneToOneField('SiteUser')
    username        = models.CharField('googlename', max_length=128, unique=True)
    
    @property
    def profile_buzz(self):
        return 'http://www.google.com/profiles/%s#buzz' % self.username


    @property
    def atom_buzz(self):
        return 'http://buzz.googleapis.com/feeds/%s/public/posted' % self.username

    def __unicode__(self):
        return self.username


TruncateOptions = {'truncate': 0,
                   'split': 1,
                   'link': 2}


class UserSettings(models.Model):
    usetag      = models.BooleanField(default=False)
    mark        = models.CharField(max_length=140)
    longmsg     = models.IntegerField(default=TruncateOptions['link'])
    longlinktext = models.CharField(default="I've published a Buzz too long for twitter here: ", max_length=110)
    paused      = models.BooleanField(default=False)
    siteuser = models.OneToOneField('SiteUser')
    
    def __unicode__(self):
        return self.siteuser.googleprofile.username



class SiteUser(models.Model):
    """User relating TwitterAccount with GoogleProfile models"""

    created_at  = models.DateTimeField('created', auto_now_add=True)
    modified_at = models.DateTimeField('modified', auto_now=True)
    lasttimeparsed_at = models.DateTimeField('lasttimeparsed', blank=True, null=True)
    userhash    = models.CharField(max_length=64) # sha256
    
    def __unicode__(self):
        return self.googleprofile.username



class Buzz(models.Model):
    """
    Used to store buzzs after getting them from Google and before successfully posting them 
    on Twitter. After the twitter posting they must be deleted to not clodge the database
    """
    created_at  = models.DateTimeField('created', auto_now_add=True)
    failed_posting = models.BooleanField(default=False)
    failed_posted_at = models.DateTimeField('failed_posted_at', blank=True, null=True)
    buzzid = models.CharField(max_length=255)
    retries = models.IntegerField('retries', default=0)

    content = models.TextField('content')
    buzzlink = models.URLField('buzz link')
    commentslink = models.URLField('comments link', blank=True)
    links   = models.TextField('links') # links, separated by | chars
    user    = models.ForeignKey('SiteUser')
    published_on_twitter = models.BooleanField('published', default=False)
 
    def __unicode__(self):
        return self.user.googleprofile.username
    
class GoogleForm(forms.Form):
    """
    Simple Google username request form
    """
    googlename = forms.CharField(max_length=128, widget=forms.TextInput(attrs={'size': '70'}))

