import urllib, urllib2

class GetGProfileException(Exception): pass

def GetUserTopicURL(gusername):
    """
    Receives a Google username like 'juanjux' or 'juanjux@gmail.com' and returns
    the Google Buzz topic URL for the push server. Can raise a GetFProfileException.
    """
    
    if '@' not in gusername:
        email = gusername + '@gmail.com'
    else:
        email = gusername
        
    webfingerurl = 'http://www.google.com/s2/webfinger/?q=%s' % urllib.quote(email)
    res = urllib2.urlopen(webfingerurl)    
    lines = res.readlines()
    
    if len(lines) < 2:
        # Error
        raise GetGProfileException('Could not get user Buzz URL')
        
    buzzurl = ''
    for line in lines:
        if "<Link rel='http://schemas.google.com/g/2010#updates-from' href=" in line:
            try:
                #line.split()[2] = "href='http://buzz.googleapis.com/feeds/116435738822984996091/public/posted'"
                buzzurl = line.split()[2].split('=')[1].replace("'", "").strip()
            except IndexError:
                raise GetGProfileException('Could not get user Buzz URL, odd format for line: %s' % line)
                
    if not buzzurl:
        raise GetGProfileException('Could not get user Buzz URL, linkrel not found on webfinger answer, probably user doesnt exists')
        
    return buzzurl

if __name__ == '__main__':
    
    print GetUserTopicURL('juanjux@gmail.com')


