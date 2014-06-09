import oauth
import oauthtwitter
import twitter
import settings
from main.models import TruncateOptions, TwitterAccount, PushSubscription


def execute_command(cmd, user, messenger):
    realcmd = cmd.strip().split(':', 1)[1]
    cmdtokens = realcmd.split()
    cmdfirst = cmdtokens[0].lower()
    
    usettings = user.usersettings
    if cmdfirst != 'cancel':
        twittername = user.twitteraccount.name
    queue = '/queue/listener'
    cmdmsg = ''

    if cmdfirst == 'cancel':
        googleprofile = user.googleprofile
        try:
            twacc = user.twitteraccount
            cmdmsg = 'cmdrpl__' + twittername + '|' + 'Your service by buzz2tweet.com has been cancelled'
        except (TwitterAccount.DoesNotExist, UnboundLocalError):
            # Probable is cancelling before even completing the wizard
            pass
        
        # Set userdeleted = True in the PushSubscription if it does exists (which SHOULD)
        pushsubs = PushSubscription.objects.filter(googleprofile = googleprofile)
        if len(pushsubs) == 1:
            pushsub = pushsubs[0]
            pushsub.userdeleted = True
            pushsub.googleprofile = None # it will be deleted on the user.delete()
            messenger.sendmessage(queue, 'unsubscribefeed__%d__%d' % (pushsub.id, googleprofile.id))
            # the subscription will be deleted when the unsubscription request comes to the callback
            pushsub.save()
            
        # Nuke the SiteUser (the onetoone keys pointing to him should delete in cascade)
        try:
            user.delete()
        except AssertionError, e:
            # Probably already deleted by another listener
            print 'AssertionError trying to delete user, probably already deleted'

    elif cmdfirst == 'pause':
        usettings.paused = True
        usettings.save()

        cmdmsg = 'cmdrpl__' + twittername + '|' + 'Your service by buzz2tweet.com has been paused. Write a buzz starting with "buzz2tweet: resume" to resume'

    elif cmdfirst == 'resume':
        usettings.paused = False
        usettings.save()

        cmdmsg = 'cmdrpl__' + twittername + '|' + 'Your service by buzz2tweet.com has been resumed'

    elif cmdfirst in ['use-tag', 'usetag']:
        # Check that the user specified a tag
        if len(cmdtokens) == 1:
            cmdmsg = 'cmdrpl__' + twittername + '|' + 'Error:you must specify a tag when using the usetag command, like "buzz2tweet: usetag #b2t"'

        else:
            usettings.usetag = True
            usettings.mark = cmdtokens[1]
            usettings.save()
            cmdmsg = 'cmdrpl__' + twittername + '|' + 'I will only publish buzzs with the %s tag on them; buzz a "buzz2tweet: dontusetag" to disable' % cmdtokens[1]


    elif cmdfirst in ['dont-use-tag', 'dontusetag']:
        usettings.usetag = False
        usettings.save()

        cmdmsg = 'cmdrpl__' + twittername + '|' + 'From now on all you buzzs will be tweeted; buzz a "buzz2tweet: usetag #tag" to change' 

    elif cmdfirst == 'excess-link' or cmdfirst == 'excesslink':
        if len(cmdtokens) == 1:
            cmdmsg = 'cmdrpl__' + twittername + '|' + 'Error:using "excesslink" you\'ve to specify text before the link like "buzz2tweet: excesslink I published a long buzz here"'

        elif len(' '.join(cmdtokens[1:])) > 119:
            cmdmsg = 'cmdrpl__' + twittername + '|' + 'Error:the text you specified for the "excesslink" option exceeds 119 characters'

        else:
            usettings.longmsg = TruncateOptions['link']
            usettings.longlinktext = ' '.join(cmdtokens[1:])
            usettings.save()
            cmdmsg = 'cmdrpl__' + twittername + '|' + 'From now on all your buzzs longer than 140 will be linked'


    elif cmdfirst == 'excess-truncate' or cmdfirst == 'excesstruncate':
        usettings.longmsg = TruncateOptions['truncate']
        usettings.save()

        cmdmsg = 'cmdrpl__' + twittername + '|' + 'From now on all your buzzs longuer than 140 will be truncated'

    elif cmdfirst == 'excess-split' or cmdfirst == 'excesssplit':
        usettings.longmsg = TruncateOptions['split']
        usettings.save()

        cmdmsg = 'cmdrpl__' + twittername + '|' + 'From now on all your buzzs longuer than 140 will be splitted on several numbered tweets'
 
    if cmdmsg:       
        messenger.sendmessage(queue, cmdmsg)