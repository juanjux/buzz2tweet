#!/usr/bin/env python

import sys, logging, time, socket, re, logging, logging.handlers
from datetime import datetime, timedelta
import feedparser
import stomp
sys.path = ['/home/juanjux/webapps/django/buzz2tweet', '/home/juanjux/webapps/django', '/home/juanjux/lib/python2.5', '/home/juanjux/webapps/django/lib/python2.5'] + sys.path
from pprint import pprint
from traceback import print_exc, format_exc

from buzz2tweet import settings
from buzz2tweet.buzzutils.utils import shortenlinks_removetags
from buzz2tweet.buzzutils.cmdinterpreter import execute_command
from buzz2tweet.stompparts.stomputils import StompMessenger
from buzz2tweet.pubsubhubbub.push_subscriber import subscribe_feed
from buzz2tweet.pubsubhubbub.buzzutils import GetUserTopicURL, GetGProfileException

import buzz2tweet.buzzutils.bitly as bitly
import oauth, oauthtwitter, twitter

from django.core.management  import setup_environ
from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError


setup_environ(settings)
from main.models import Buzz, SiteUser, BuzzFeedParsingException, TruncateOptions, Notification, GoogleProfile, PushSubscription


# XXX FIXME: CAMBIAR
MAXRETRIES = 10

def run_server():
    while 1:
        time.sleep(5)

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


class Buzz2TweetListener(object):
    
    def __init__(self):
        self.logger = get_listener_logger()
        self.logger.debug('Listening starting')
        
        self.bitlyapi = bitly.Api(login=settings.BITLY_LOGIN, apikey=settings.BITLY_APIKEY)
        self.recompiled = re.compile("(https?://[^\s]+)")
        self.cmdre = re.compile(u'^buzz2tweet:|^buzz2twitter:|^buzz2tweet :|^buzz2twitter :', re.I)
        self.messenger = StompMessenger()
        self.queuepath = '/queue/listener'
    
    
    def on_error(self, headers, message):
        self.logger.error('Listener received error: %s' % str(message))
        
        
    def on_message(self, headers, message):
        try:
            msg = 'listener: msg received: ' + str(message)
            self.logger.debug(msg)
            
            msg, body = message.split('__', 1)
            
            if msg == 'publish':
                self.post_buzz2twitter(body)
                
            elif msg == 'cmdrpl':
                self.post_twitcommand(body)
                
            elif msg == 'fetchuserfeed':
                self.fetchuserfeed(body)
            
            elif msg == 'notification':
                self.processnotification(body)
                
            elif msg == 'subscribefeed':
                self.subscribefeed(body)
                
            elif msg == 'unsubscribefeed':
                self.unsubscribefeed(body)
                
        except Exception, e:
            self.logger.error('Undhandled exception on on_message: ')
            self.logger.error(format_exc())
        
        
    def post_buzz2twitter(self, message):
        """
        Publish the buzz on twitter
        """
        
        msg = 'listener.post_buzz2twitter: msg received: ' + message
        self.logger.debug(msg)
 
        try:       
            # (currently we only manage publish__id)
            buzzid = int(message)
            try:
                buzz = Buzz.objects.get(id=buzzid) 
                content = buzz.content
            
                siteuser = buzz.user
                twaccount = siteuser.twitteraccount
            except ObjectDoesNotExist:
                self.logger.debug('Ignoring user %d which doesnt have TwitterAccount yet' % siteuser.id)
                return
            
            oauthtoken = oauth.OAuthToken.from_string(twaccount.token)
            twapi = oauthtwitter.OAuthApi(settings.CONSUMER_KEY, settings.CONSUMER_SECRET, oauthtoken)
            
            # Remove the #b2t or whatever tag the user is using
            if siteuser.usersettings.usetag and siteuser.usersettings.mark in content:
                content = content.replace(siteuser.usersettings.mark, u'')
            
            if len(content) > 140:
                # Long tweet, see the user options for the case
                if siteuser.usersettings.longmsg == TruncateOptions['truncate']:
                    content = content[:140]
                    
                elif siteuser.usersettings.longmsg == TruncateOptions['link']:
                    shortened = self.bitlyapi.shorten(buzz.buzzlink)
                    content = siteuser.usersettings.longlinktext + u' ' + shortened
                    
                # PostUpdates will automatically split the message if it is longer than 140, so there
                # is no need to do anything special for siteuser.settings.longmsg == TruncateOptions['split']
                
            try:
                msg = u'Publishing on Twitter: ' + content,
                self.logger.info(msg)
                twapi.PostUpdates(content.encode('utf-8').strip())  
                buzz.published_on_twitter = True
                if buzz.failed_posting:
                    buzz.failed_posting = False
                buzz.retries = 0
                buzz.save()
            except Exception, e:
                tb = format_exc()
                msg = 'Exception publishing on twitter!!! ' + '\n' + tb
                self.logger.error(tb)
                buzz.failed_posting = True
                buzz.retries += 1
                
                if buzz.retries > MAXRETRIES:
                    msg = 'Deleting buzz because it failed %d times' % MAXRETRIES
                    self.logger.warning(msg)
                    buzz.delete()
                else:
                    buzz.save()
                    self.logger.debug('re-enqueuing message for buzz %d' % buzzid)
                    self.messenger.sendmessage('/queue/listener', 'publish__%d' % buzzid)
            buzz.save()
        except Exception, e:
            tb = format_exc()
            msg = 'listener.post_buzz2twitter failed: ' + tb
            self.logger.error(msg)
        
        
    def post_twitcommand(self, message):
        """
        Publish replies to user commands on twitter
        """
        
        try:
            msg =  u'listener.post_twitcommand: msg received: ' + message
            self.logger.debug(msg)
            
            twapibot = twitter.Api(username=settings.BOT_USERNAME, password=settings.BOT_PASSWD)
            name, text = message.split('|')
            replyText = '@%s %s' % (name, text)
            msg = 'Command interpreter sending: ' + replyText
            self.logger.debug(msg)
            twapibot.PostUpdate(replyText)
        except Exception, e:
            tb = format_exc()
            msg = 'listener.posttwitcommand failed: ' + tb
            self.logger.error(msg)
        
        
        
    def fetchuserfeed(self, message):
        """
        Parse a user Buzz Atom feed
        """
        
        profile = None
        
        msg =  'listener.fetchuserfeed: msg received: ' + message
        self.logger.debug(msg)
        
        try:
            siteuserid = int(message.strip())
            siteuser = SiteUser.objects.get(id=siteuserid)
            
            if siteuser.usersettings.usetag:
                tagre = re.compile(siteuser.usersettings.mark)
                
            profile = siteuser.googleprofile
            try:
                (newentries, newest_date) = profile.get_new_entries()
            except BuzzFeedParsingException, e:
                msg = 'Exception parsing feed for user %d: %s' % (siteuser.id, str(e))
                self.logger.debug(msg)
                return
            
            self.logger.debug('There are %d new entries for this user' % len(newentries))
            if len(newentries) > 0:
                for entry in newentries:
                    buzzcontent = shortenlinks_removetags(entry['content'].value, self.recompiled, self.bitlyapi)
                    print 'XXXXXXXXXXXXXX buzzxcontent: ' + str(buzzcontent)
 
                    if self.cmdre.search(buzzcontent):
                        # Is a command, execute it but don't save the buzz
                        self.logger.info(u'parsing command for: %s' % buzzcontent)
                        execute_command(buzzcontent, siteuser, self.messenger)
                        continue
                    
                    # User want to publish only buzzs with tag? is there a tag?
                    if siteuser.usersettings.paused or (siteuser.usersettings.usetag and not tagre.search(buzzcontent)):
                        continue
                    
                    newbuzz = Buzz(buzzid = entry['id'],
                                   content = buzzcontent,
                                   links = entry['links'],
                                   user = siteuser,
                                   buzzlink = entry['buzzlink'])
                    
                    if entry.has_key('comments'):
                        newbuzz.commentslink = entry['comments']
                        
                    msg = u'Saving new buzz: '  + buzzcontent
                    self.logger.info(msg)
                    newbuzz.save()
                    
                    # Send a message for the listener.post_buzz2twitter to post the status
                    self.messenger.sendmessage('/queue/listener', 'publish__%d' % newbuzz.id)
 
                profile.firsttime = False
                self.logger.info('Asignando a lastbuffread_at la fecha: ' + str(newest_date))
                profile.lastbuffread_at = newest_date
                profile.retries = 0
                profile.save()
                
        except Exception, e:
            tb = format_exc()
            msg = 'listener.fetchuserfeed failed, ignoring the error (will be reparsed again)\n' + tb
            self.logger.error(msg)
            
            if (profile):
                # Currently I'm not using the retries, but could be interesting for doing cleanups from
                # time to time
                profile.retries += 1
                profile.save()
        
        
    def processnotification(self, notif_id):
        """
        Parse an Atom notificaton received from the pubsubhubbub callback
        """
        
        
        msg =  'listener.processnotification: msg received: ' + str(notif_id)
        self.logger.debug(msg)
        notif = Notification.objects.get(id = int(notif_id))
        googleprofile = notif.googleprofile
        siteuser = googleprofile.siteuser
        
        #self.logger.debug('XXX 1')
        
        if siteuser.usersettings.usetag:
            tagre = re.compile(siteuser.usersettings.mark)
 
        feedparse_result = feedparser.parse(notif.text.encode('utf-8'))
        
        newest_date = None
        newentries = []
        
        #self.logger.debug('XXX 2')
        ld = self.logger.debug # XXX
        
        for entry in feedparse_result.entries:
            #self.logger.debug('XXX 3')
            
            try:
                d  = entry.published_parsed
            except AttributeError:
                # Sometimes posts doesnt have published field and are not published on Buzz :-?
                #ld('XXX 4')
                continue
            #pprint(entry)
            date_buzz = datetime(d[0], d[1], d[2], d[3], d[4], d[5])
 
            # Note: if the user is new lastbuffread_at == created_at
            ld('XXX date_buzz: %s lastbuffread_at: %s' % (str(date_buzz), str(googleprofile.lastbuffread_at)))
            if date_buzz > googleprofile.lastbuffread_at:
                #ld('XXX 5')
                # Get links/photos (if there is any)
                linkscontent = [] # Only the URL
                linkslist = [] # Dict with all the data
                
                buzzlink = comments = links = ''
                for link in entry.links:
                    if link.rel == u'enclosure':
                        if link.href not in linkscontent: # avoid duplicates
                            linkscontent.append(link.href)
                            linkslist.append({'href': link.href, 'title': link.get('title', ''), 'type': link.type})
                    elif link.rel == u'alternate':
                        buzzlink = link.href
                    elif link.rel == u'replies':
                        comments = link.href
    
                links = '|'.join(linkscontent)
                buzzcontent = shortenlinks_removetags(entry.content[0].value, self.recompiled, self.bitlyapi)
 
                #ld('XXX 6')               
                if settings.CMDRE.search(buzzcontent):
                    #ld('XXX 7')
                    # Is a command, execute it but don't save the buzz
                    self.logger.info(u'parsing command for: %s' % buzzcontent)
                    execute_command(buzzcontent, siteuser, self.messenger)
                    continue
                
                # User want to publish only buzzs with tag? is there a tag?
                if siteuser.usersettings.paused or (siteuser.usersettings.usetag and not tagre.search(buzzcontent)):
                    #ld('XXX 8')
                    continue
                
                newbuzz = Buzz(buzzid   = entry.id,
                               content  = buzzcontent,
                               links    = links,
                               user     = siteuser,
                               buzzlink = buzzlink)
                
                if comments != '':
                    newbuzz.commentslink = comments
                    
                msg = u'Saving new buzz: '  + buzzcontent
                self.logger.info(msg)
                try:
                    #ld('XXX 9')
                    newbuzz.save()
                except IntegrityError:
                    # User probably issued a 'cancel' command just before this message
                    self.logger.warning('Received IntegrityError for user while saving Buzz, probably already deleted')
                    continue
                    
                
                #ld('XXX 10')
                # Send a message for the listener.post_buzz2twitter to post the status
                self.logger.info('sending message to queue publish__%d' % newbuzz.id)
                self.messenger.sendmessage('/queue/listener', 'publish__%d' % newbuzz.id)
                
                #ld('XXX 11')
    
                if newest_date == None or date_buzz > newest_date:
                    newest_date = date_buzz
    
        if len(feedparse_result.entries) == 0:
            self.logger.warning('There are 0 entries in the feed, could be a parse error')
            if feedparse_result.has_key('bozo_exception'):
                self.logger.warning('bozo_exception is: ' + str(feedparse_result.bozo_exception))
                
        else:
            # Update the date of the last buzz read and reset the retries
            self.logger.debug('new lastbuzzread_at is: ' + str(newest_date))
            if newest_date != None:
                googleprofile.firsttime = False
                googleprofile.lastbuffread_at = newest_date
                
            googleprofile.retries = 0
            googleprofile.save()
            
            
    def subscribefeed(self, message):
        msg =  'listener.subscribefeed: msg received: ' + str(message)
        self.logger.debug(msg)
        
        googleprof = GoogleProfile.objects.get(id = int(message))
     
        try:
            topic_url    = GetUserTopicURL(googleprof.username)
        except GetGProfileException, e:
            self.logger.error('ERROR: Could not get topic_url for the user %s: %s' % (googleprof.username, str(e)))
            return
        
        callback_url = 'http://%s%s' % (Site.objects.get_current(),
                                        reverse('pubsubcallback', args=[googleprof.id]))
            
        # We wont check if the user is already subscribed, it doesn't harm to subscribe twice, but we
        # check that the notification objects exists for the user for updating it (creating it if not)
        subscriptions = PushSubscription.objects.filter(googleprofile = googleprof)
        if len(subscriptions) == 1:
            subscription = subscriptions[0]
            subscription.topic_url = topic_url
            subscription.googleprof = googleprofile
            subscription.renewed_at = datetime.now()
        else:
            subscription = PushSubscription(confirmed=False,
                                            topic_url=topic_url,
                                            googleprofile=googleprof,
                                            renewed_at=datetime.now())
            
        # Async subscription request; the server will reply later calling the callback and from there
        # the subscription will be considered enabled
        self.logger.debug('Subscribing user: %s' % googleprof.username)
        self.logger.debug('To topic URL: %s' % topic_url)
        self.logger.debug('Using callback: %s' % callback_url)
        subscribe_feed(topic_url, callback_url, subscribe=True)
        subscription.save()
        
        
    def unsubscribefeed(self, message):
        msg =  'listener.unsubscribefeed: msg received: ' + str(message)
        self.logger.debug(msg)
        # Dont try to instantiate googleprofileid, probably is already deleted
        try:
            pushsubid, googleprofileid = message.split('__')
            pushsub = PushSubscription.objects.get(id = int(pushsubid))
            callback_url = 'http://%s%s' % (Site.objects.get_current(),
                                            reverse('pubsubcallback', args=[googleprofileid]))
                
            # Async unsubscription request; the server will reply later calling the callback and from there
            # the subscription will be deleted
            subscribe_feed(pushsub.topic_url, callback_url, subscribe=False)
        except Exception, e:
            self.logger.error('Exception on unsubscribefeed: ')
            self.logger.error(format_exc())
 
        
def main():
    socket.setdefaulttimeout(5)
    queue = '/queue/listener'        
    hosts=[('localhost', 61613)]
    connected = False
    
    #logging.basicConfig()
    logger = get_listener_logger()
    
    while not connected:
        try:
            conn = stomp.Connection(host_and_ports=hosts)
            conn.set_listener('Buzz2TweetListener', Buzz2TweetListener())
            conn.start()
            conn.connect()
            
            conn.subscribe(destination=queue, ack='auto')
            connected = True
        except socket.error, e:
            msg = 'Listener.main retrying connection because of error: ' + str(format_exc())
            logger.warning(msg)
        
    if connected:
        logger.info('Starting listener server')
        run_server()
    
if __name__ == '__main__': main()