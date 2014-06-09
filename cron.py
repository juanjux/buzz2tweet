import sys
import os
import time
from traceback import format_exc

sys.path = ['/home/juanjux/webapps/django/web', '/home/juanjux/webapps/django', '/home/juanjux/lib/python2.5', '/home/juanjux/webapps/django/lib/python2.5'] + sys.path

"""
RUNNING DJANGO METHODS AS CRON TASKS
------------------------------------

Use this script to run Django methods from the console or the crontab. For example, if
we want to call the method update_tweets from web.tweets.utils we can do:

$ python /home/juanjux/trunk/web/cron.py tweets.utils update_tweets\(\)

If we wanted to add a call to this script in the crontab running every minute, we should "su" to the 
user running the apache process, exec "crontab -e" and add the line:

* * * * *    /usr/local/jaratech/python2.5/bin/python /home/sticky/projects/web/cron.py tweets.utils update_tweets\(\)

(see the manpage or the zillion tutorials on the web for other time specifications on the 
crontab file)
"""

# Get the 'web' directory and add it to sys.path
envdir = os.path.split(os.path.dirname(__file__))[0]
sys.path.append(envdir)

from django.core.mail import send_mail

# Add the settings module path to the DJANGO_SETTINGS_MODULE environment var. Once
# this is done, we're ready to run methods in out Django environment
os.environ['DJANGO_SETTINGS_MODULE'] = 'web.settings'

MAXTRIES = 3
tries = 0

while tries <= MAXTRIES:
    try:
        tries += 1
        module_name = sys.argv[1]
        function_name = ' '.join(sys.argv[2:])
        exec('import %s' % module_name)
        exec('%s.%s' % (module_name, function_name))
    except Exception, e:
        if tries > MAXTRIES:
            send_mail('Cron.py failed %d times for JuanjoAlvarez.net' % tries, 
                  'Sys.argv: %s\n\n\nError: \n\n %s' % (str(sys.argv), format_exc()), 
                  'juanjo@juanjoalvarez.net', ['juanjux@gmail.com'], 
                  fail_silently=False)
        else:
            time.sleep(60)
    else:
        sys.exit(0)
