import re
import feedparser
from datetime import datetime
from buzz2tweet import settings
from buzz2tweet.main.models import Buzz
from buzz2tweet.buzzutils.cmdinterpreter import execute_command
from buzz2tweet.buzzutils.bitly import BitlyError
from buzz2tweet.stompparts.stomputils import StompMessenger
from BeautifulSoup import BeautifulSoup

"""
# DEBUG
LOGGER = None

def get_listener_logger():
    import logging
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

def shortenlinks_removetags(content, recompiled, bitlyapi):
    """
    Shorten the links of a text using the bit.ly API and then remove the html tags
    """
    
    # DEBUG
    #logger = get_listener_logger()
    
    soup = BeautifulSoup(content)
    
    # First shorten the links
    someshortened = False
    
    if recompiled.search(content):
        urls = []
        
        soup = BeautifulSoup(content)
        links = soup.findAll('a')
        
        for link in links:
            orig    = link.text
            try:
                shortened = bitlyapi.shorten(link.text).decode('utf-8')
            except BitlyError, e:
                # Already shortened?
                shortened = link.text
            urls.append( (orig, shortened) )
            
        for urltuple in urls:
            someshortened = True
            if len(urltuple[0]) > len(urltuple[1]):
                content = content.replace(urltuple[0], urltuple[1])
                
    if someshortened:
        # Update the soup with the new content with shortened links
        soup = BeautifulSoup(content)
        
    # Remove all tags
    notagscontents = ''.join(BeautifulSoup(content).findAll(text=True))
        
    return notagscontents
 

def parse_buzzs(atom, googleprofile, logger):
    
    messenger = StompMessenger()
    siteuser  = googleprofile.siteuser
    
    if siteuser.usersettings.usetag:
        tagre = re.compile(siteuser.usersettings.mark)
        
    feedparse_result = feedparser.parse(atom)
    
    newest_date = None
    newentries = []
        
    logger.info("XXX 1")
    for entry in feedparse_result.entries:
        
        logger.info("XXX 2")
        
        try:
            d  = entry.published_parsed
        except AttributeError:
            # Sometimes posts doesnt have published field and are not published on Buzz :-?
            logger.info("XXX 3")
            continue
        logger.info("XXX 4")
        #pprint(entry)
        date_buzz = datetime(d[0], d[1], d[2], d[3], d[4], d[5])

        if ( googleprofile.firsttime and date_buzz > googleprofile.created_at) or     \
           ((not googleprofile.firsttime) and date_buzz > googleprofile.lastbuffread_at): \
            # Get links/photos (if there is any)
            linkscontent = []
            logger.info('XXX 5')
            linkslist = []
            
            buzzlink = comments = links = linkslist_str = ''
            logger.info("XXX 6")
            for link in entry.links:
                if link.rel == u'enclosure':
                    if link.href not in linkscontent: # avoid duplicates
                        linkscontent.append(link.href)
                        linkslist.append({'href': link.href, 'title': link.title, 'type': link.type})
                        linkslist_str += link.href
                elif link.rel == u'alternate':
                    buzzlink = link.href
                elif link.rel == u'replies':
                    comments = link.href

            links = '|'.join(linkslist_str)
            buzzcontent = entry.content[0].value
            
            logger.info('XXX 7')           
                
            if settings.CMDRE.search(buzzcontent):
                # Is a command, execute it but don't save the buzz
                logger.info(u'parsing command for: %s' % buzzcontent)
                execute_command(buzzcontent, siteuser, messenger)
                logger.info('XXX 8')
                continue
            
            # User want to publish only buzzs with tag? is there a tag?
            if siteuser.usersettings.paused or (siteuser.usersettings.usetag and not tagre.search(buzzcontent)):
                logger.info('XXX Ignoring, paused or with usetag without tag')
                continue
            
            newbuzz = Buzz(buzzid   = entry.id,
                           content  = buzzcontent,
                           links    = links,
                           user     = siteuser,
                           buzzlink = buzzlink)
            
            if comments != '':
                newbuzz.commentslink = comments
                
            msg = 'Saving new buzz: '  + unicode(buzzcontent).encode('utf-8')
            logger.info(msg)
            newbuzz.save()
            
            # Send a message for the listener.post_buzz2twitter to post the status
            logger.info('sending message to queue publish__%d' % newbuzz.id)
            messenger.sendmessage('/queue/listener', 'publish__%d' % newbuzz.id)            

            if newest_date == None or date_buzz > newest_date:
                newest_date = date_buzz

    if len(feedparse_result.entries) == 0:
        logger.warning('There are 0 entries in the feed, could be a parse error')
        if feedparse_result.has_key('bozo_exception'):
            logger.warning('bozo_exception is: ' + str(feedparse_result.bozo_exception))
            
    else:
        # Update the date of the last buzz read and reset the retries
        logger.debug('new lastbuzzread_at is: ' + str(newest_date))
        if newest_date != None:
            googleprofile.firsttime = False
            googleprofile.lastbuffread_at = newest_date
            
        googleprofile.retries = 0
        googleprofile.save()
