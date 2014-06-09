import logging
import logging.handlers
import re
from datetime import datetime, timedelta
from urllib2 import HTTPError

from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext, Context, loader, VariableDoesNotExist
from django import http

from buzz2tweet import settings
from buzz2tweet.main.models import TwitterAccount, SiteUser, GoogleProfile, Buzz, GoogleForm, UserSettings, Notification, PushSubscription
from buzz2tweet.stompparts.stomputils import StompMessenger
from buzz2tweet.pubsubhubbub.buzzutils import GetUserTopicURL, GetGProfileException

import oauth
import hashlib
import feedparser
from oauthtwitter import OAuthApi
from django.http import HttpResponseRedirect, HttpResponse
import settings

LOGGER = None

def get_fe_logger():
    global LOGGER

    if not LOGGER:
        LOGGER = logging.getLogger('frontend')
        LOGGER.setLevel(settings.LOGLEVEL)
        handler = logging.handlers.RotatingFileHandler(settings.LOG_FRONTEND, maxBytes=10485760, backupCount=10)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)    
        LOGGER.addHandler(handler)
    
    return LOGGER
    

################# views ############################

def index(request):
    logger = get_fe_logger()
    logger.info('On index')
    error = None

    if request.method == 'POST': # Form submitted
        form  = GoogleForm(request.POST)
        if form.is_valid():
            googleaccount = form.cleaned_data['googlename'].strip()
            
            topicurl = ''
            
            # Check that its an email and we can get the buzz topic url
            isFine = re.match(r"(?:^|\s)[-a-z0-9_.]+@(?:[-a-z0-9]+\.)+[a-z]{2,6}(?:\s|$)",googleaccount, re.IGNORECASE)
            if isFine:
                # Check that we can get the topic url for Buzz
                try:
                    topicurl = GetUserTopicURL(googleaccount)
                except GetGProfileException:
                    isFine = False
                    
            if not isFine:
                error = """Invalid Google Account (you entered "%s". Please check that it includes the @gmail.com or @googlemail.com,
                           for example "joe@gmail.com" is correct, "joe" or "joe@gmail" is not.
                        """ % googleaccount
                logger.info('Invalid Google Account submitterd by the user: ' + googleaccount)
                
            else:
                if len(GoogleProfile.objects.filter(username=googleaccount)) > 0:
                    error = """
                            Google account is already registered! Please write a Buzz with the content "buzz2tweet: cancel"
                            if you want to cancel the service for your Buzz account.
                            """
                    logger.info('UserError: Google account already registered for %s' % googleaccount)
                    
                else:
                    request.session['gprofileusername'] = googleaccount
                    return HttpResponseRedirect('/twitterstep/')
    else:
        form = GoogleForm()
    return render_to_response("index.html", {}, RequestContext(request, {'form': form, 'error': error}))


def twitterstep(request):
    logger = get_fe_logger()
    logger.info('On twitterstep')
            
    if not request.session.has_key('gprofileusername'):
        logger.debug('User doesnt have session on twitterstep, redirecting to /')
        return HttpResponseRedirect('/')
        
    return render_to_response("twitterstep.html", {}, RequestContext(request, {}))


def auth(request):
    logger = get_fe_logger()
    logger.info('On auth')
    
    if not request.session.has_key('gprofileusername'):
        logger.debug('User doesnt have session on auth(), redirecting to /')
        return HttpResponseRedirect('/')
        
    twitter = OAuthApi(settings.CONSUMER_KEY, settings.CONSUMER_SECRET)
    request_token = twitter.getRequestToken()
    request.session['request_token'] = request_token.to_string()
    authorization_url = twitter.getAuthorizationURL(request_token)
    logger.debug('Sending user to authorization URL %s' % authorization_url)
    return  HttpResponseRedirect(authorization_url)


def settingsstep(request, userid=None):
    logger = get_fe_logger()
    logger.info('On settingsstep')
    
    # We could get here trought a GET (user saved a bookmark to the settings)
    if userid and len(userid) == 64:
        userhash = userid
        
    elif not request.session.has_key('gprofileusername'):
        logger.debug('User doesnt have session, redirecting to /')
        return HttpResponseRedirect('/')
        
    gprofile = GoogleProfile.objects.get(username=request.session['gprofileusername'])
    siteuser = gprofile.siteuser
    usettings = siteuser.usersettings
    
    if request.method == 'POST':
        usettings.longmsg = int(request.POST['longmsg'])
        
        if request.POST.has_key('usetag') and request.POST.has_key('mark'):
            usettings.usetag = True
            usettings.mark = request.POST['mark']
        else:
            usettings.usetag = False
            
        if request.POST['longmsg'] == '2' and request.POST.has_key('longlinktext'):
            usettings.longlinktext = request.POST['longlinktext']
            
        usettings.save()
        logger.debug('Saved settings for user %d' % siteuser.id)
        return HttpResponseRedirect('/docs/')
    
    return render_to_response("settingsstep.html", {}, RequestContext(request, {'userhash': request.session['siteuserhash']}))


def docsstep(request):
    return render_to_response("docsstep.html", {}, RequestContext(request, {}))


# FIXME: Lot of return-spaguetti...
def pubsub_callback(request, gprofileid):
    logger = get_fe_logger()
    logger.info('On pubsub callback, gprofileid |%s|' % str(gprofileid))
 
    # Unsubscriptions for a GoogleProfile already deleted can arrive, so don't use get_object_or_404
    googleprofile = None
    
    profiles = GoogleProfile.objects.filter(id=int(gprofileid))
    if len(profiles) > 0: googleprofile = profiles[0]

    # POST = new item notifications
    if request.method == 'POST':
        
        logger.info('POST method, raw_post_data:')
        logger.info(str(request.raw_post_data))
        
        # Save the atom, user data and send a request for a listener to process it so the
        # hub doesn't have to wait
        if not googleprofile:
            # Notification for a deleted profile
            logger.info('push_callback.post: received notification for deleted profile %d!' % int(gprofileid))
            return HttpResponse(status=404)
            
        notif = Notification(text = request.raw_post_data, googleprofile = googleprofile)
        notif.save()
        messenger = StompMessenger()
        messenger.sendmessage('/queue/listener', 'notification__%d' % notif.id)
        
        return HttpResponse(status=200)

    # GET = subscription or unsubscription confirmation
    elif request.method == 'GET':
        rg = request.GET
        
        challenge = rg.get(u'hub.challenge', '')
        topic_url  = rg.get(u'hub.topic', None)
        logger.debug('XXX topic_url en GET: %s' % topic_url)
        mode       = rg.get(u'hub.mode', None)
        lease      = rg.get(u'hub.lease_seconds', 0)
        
        if not mode or not topic_url:
            logger.warning('Returning 404 in callback/get because not mode or topic')
            return HttpResponse(status=404)
            
        if mode == 'subscribe':
            logger.debug('push_callback: its a subscription request')
            if not googleprofile:
                logger.warning('Returning 404 in callback/subscribe because no googleprofile exists')
                return HttpResponse(status=404)
                
            pushsub = get_object_or_404(PushSubscription, googleprofile=googleprofile)
            pushsub.confirmed = True
            pushsub.renewed_at = datetime.now()
            pushsub.lease_time = int(lease)
            pushsub.topic_url = topic_url.strip()
            pushsub.save()
            logger.info('push_callback: profile %d correctly subscribed' % int(gprofileid))
                
        elif mode == 'unsubscribe':
            logger.debug('push_callback: its an unsubscription request for topic_url:')
            logger.debug(topic_url)
            
            if googleprofile:
                pushsub = PushSubscription.objects.filter(googleprofile=googleprofile)[0]
                logger.debug('Have profile')
                if pushsub.userdeleted:
                    logger.info('push_callback: profile %d (gprofile existed) correctly unsubscribed ' % int(gprofileid))
                    googleprofile.delete()
                    pushsub.delete()
                    return HttpResponse(status=200)
                else:
                    logger.info('push_callback: profile %d not deleted! returning 404' % int(gprofileid))
                    return HttpResponse(status=404)
            else:
                logger.debug('No profile')
                logger.info('push_callback: is for gprofile that doesnt exists anymore, returning 200 anyway')
            
            """
            pushsubs = PushSubscription.objects.filter(topic_url=topic_url)
            
            if len(pushsubs) == 1: 
                pushsub = pushsubs[0]
                logger.info('push_callback: for pususb %d:' % pushsub.id)
                if pushsub.userdeleted:
                    if googleprofile: googleprofile.delete()
                    pushsub.delete()
                    logger.info('push_callback: profile %d correctly unsubscribed' % int(gprofileid))
                else:
                    if googleprofile:
                        # User hasn't been deleted!
                        logger.info('push_callback: user with profile %d is not deleted! returning 404' % int(gprofileid))
                        return HttpResponse(status=404)
                    else:
                        logger.info('push_callback: received notification for used deleted but with subscription, deleting sub')
                        pushsub.delete()
            else:
                logger.info('push_callback: profile %d already deleted, but returning 200 anyway' % int(gprofileid))
            """
                   
        return HttpResponse(challenge, status=200)
        
    else:
        logger.warning('No POST or GET on callback!')
    return HttpResponse(status=404)


def twitter_return(request):
    """
    Get the Twitter auth tokens, check them and then create all the user-related database models
    and subscribe to the pubsubhubbub server
    """
    
    logger = get_fe_logger()
    logger.info('On twitter_return')
    
    if not request.session.has_key('gprofileusername'):
        logger.debug('User doesnt have session on twitterreturn, redirecting to /')
        return HttpResponseRedirect('/')
        
    request_token = request.session.get('request_token', None)
    if not request_token:
        # Redirect the user to the login page,
        # So the user can click on the sign-in with twitter button
        logger.debug('User not sent to twitter by us on twitter_return()')
        return HttpResponse("We didn't sent you to twitter...")

    token = oauth.OAuthToken.from_string(request_token)

    # If the token from session and token from twitter does not match
    #   means something bad happened to tokens
    if token.key != request.GET.get('oauth_token', 'no-token'):
        del request.session['request_token']
        # Redirect the user to the login page
        logger.debug('Tokens doesnt match for user')
        return HttpResponse("Something wrong! Tokens do not match...")
                     

    twitter = OAuthApi(settings.CONSUMER_KEY, settings.CONSUMER_SECRET, token)
    try:
        access_token = twitter.getAccessToken()
    except HTTPError:
        logger.warning('Access denied on twitter.getAccessToken()')
        return HttpResponseRedirect('/')

    # Somewhat clumsy to create it again, but its the way oauthapi-twitter works...
    twitter = OAuthApi(settings.CONSUMER_KEY, settings.CONSUMER_SECRET, access_token)
    twuser = twitter.GetUserInfo()
    
    # Now that we have the Twitter account we can create all the user-related models
    googlename = request.session['gprofileusername']
    userhash = hashlib.sha256( settings.MD5SALT + googlename).hexdigest()
    
    # SiteUser
    siteuser = SiteUser(userhash=userhash)
    siteuser.save()
    
    # GoogleProfile
    gprofile = GoogleProfile(username=googlename, siteuser=siteuser)
    gprofile.save()
    # Initialize lastbuffread_at to created_at - 2 minutes (so we account for server time diffs)
    gprofile.lastbuffread_at = gprofile.created_at - timedelta(minutes=2)
    logger.debug('GProfile created_at : %s' % str(gprofile.created_at))
    logger.debug('GProfile lastbuff_at: %s' % str(gprofile.lastbuffread_at))
    gprofile.save()
    
    # UserSettings
    usettings = UserSettings(siteuser=siteuser)
    usettings.save()
    logger.info('Saved new SiteUser %d [%s]' % (siteuser.id, googlename))
 
    # TwitterAccount   
    twname = twuser.GetScreenName()
    twitteraccount = TwitterAccount(name=twname, token = access_token.to_string(), siteuser=siteuser)
    twitteraccount.save()
    
    # Send the ticket for subscribing to the push server
    messenger = StompMessenger()
    messenger.sendmessage('/queue/listener', 'subscribefeed__%d' % gprofile.id)

    return render_to_response("settingsstep.html", {}, RequestContext(request, {'userhash': userhash})) 
