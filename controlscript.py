#!/usr/bin/env python

import os, sys, commands, time

LISTENER = 'listener.py'
STOMPSERVER = '/usr/bin/ruby1.8 /usr/bin/stompserver'
DJANGO = '/home/juanjux/webapps/django/buzz2tweet/manage.py runfcgi'
USER = 'juanjux'
NUMLISTENERS = 1

PYTHONVER = 'python2.5'
PROJECTNAME = 'buzz2tweet'
PROJECTPATH = '/home/juanjux/webapps/django/%s' % PROJECTNAME
LISTENERSH    = "%s/runlistener.sh" % PROJECTPATH
MAXREQUESTS = 300
MAXSPARE = 1
MINSPARE = 1
MAXCHILDREN = None


def killprocesses(processname, user):
    buzzpscmd = 'ps aux|grep "%s" | grep python | grep -v grep| grep "%s"' % (processname, user)
    print buzzpscmd
    outputlines = commands.getoutput(buzzpscmd).splitlines()
    
    for line in outputlines:
        line = line.strip()
        if line == '': continue
        
        tokens = line.split()
        pid = tokens[1]
        
        if not pid.isdigit():
            print u'Warning: line doesnt contain numeric PID as second token: ' + line
            print u'Command was: '
            print buzzpscmd
            continue
        
        ret = os.system('kill %s' % pid)
        if ret != 0:
            print u'Warning: could not kill process %s' % pid
            continue
    
    
def startdjangofcgi(user, python, projectpath, projectname, maxrequests, method,
                    maxspare, minspare, maxchildren=None, daemonize=True):
    
    d = {'python': python,
         'projectpath': projectpath,
         'projectname': projectname,
         'maxrequests': maxrequests,
         'method': method,
         'maxspare': maxspare,
         'minspare': minspare,
         'maxchildren': maxchildren,
         'daemonize': str(daemonize)}
    
    cmd1 = "%(python)s %(projectpath)s/manage.py runfcgi socket=%(projectpath)s/%(projectname)s.sock "
    cmd2 = "maxrequests=%(maxrequests)s method=%(method)s maxspare=%(maxspare)s minspare=%(minspare)s "
    
    if maxchildren != None:
        cmd3 = "maxchildren=%(maxchildren)s daemonize=%(daemonize)s "
    else:
        cmd3 = "daemonize=%(daemonize)s "
    
    fullcmd = cmd1 + cmd2 + cmd3
    realcmd = fullcmd % d
    
    print 'Starting Django: '
    print realcmd
    
    ret = os.system('sudo -u %s %s' % (user, realcmd))
    if ret != 0:
        print 'Error: could not start Django, return code: ' + str(ret)
 
    time.sleep(1)       
    os.system('chmod 777 %s/%s.sock' % (projectpath, projectname))
 
 
def startbgprocess(process, user, nohup=True):
    
    if nohup:
        ret = os.system('sudo -u %s nohup %s&' % (user, process))
    else:
        ret = os.system('sudo -u %s %s' % (user, process))
    if ret != 0:
        print 'Error: could not start process %s as user %s' % (process, user)
 
    
def main():
    
    if os.getuid() != 0:
        print 'This script needs to be run as user root'
        sys.exit(1)
 
    if len(sys.argv) == 1:
        print 'Command missing'
        sys.exit(1)
        
    command = sys.argv[1].strip()
        
    if command == 'stop':
        # Stop services-----------------------
        print 'Stopping services...'
        #killprocesses(LISTENER, USER)
        #killprocesses(STOMPSERVER, USER)
        killprocesses(DJANGO, 'juanjux')
    
    elif command == 'start':
    # Start services----------------------
        print 'Starting services...'
        startdjangofcgi(USER, PYTHONVER, PROJECTPATH, PROJECTNAME, MAXREQUESTS, 'prefork', MAXSPARE, MINSPARE)
        #startbgprocess(STOMPSERVER, USER)
        
        #for _ in range(NUMLISTENERS):
        #    startbgprocess(LISTENERSH, USER)
            
    return 0
    

if __name__ == '__main__': sys.exit(main())
