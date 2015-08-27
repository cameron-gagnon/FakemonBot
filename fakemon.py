#! /usr/bin/env python3.4
import praw
import sqlite3
import re
import time
import logging
import logging.handlers

from configparser import ConfigParser
from sys import exit, stdout, stderr
from requests import exceptions

############################################################################
class Submissions:
    
    def __init__(self, subreddit, r):
        # subreddit to parse through
        # set to a specific sub if needed
        self.subreddit = subreddit
        # r is the praw Reddit Object
        self.r = r

    def get_titles_to_parse(self):
        # gets the subreddit, usually /r/all
        sub = self.r.get_subreddit(self.subreddit)
        # retrieves the comments from this subreddit
        # the limit is set to None, but is actually 1024
        self.submissions = sub.get_new(limit = 25)
    
    def post_title_comment(self):
        db = Database()
        # goes through each comment and 
        # searches for the keyword string
        for submission in self.submissions:
            log.debug("Going through posts") 
            title = submission.title
            ID = submission.id
            user = self.parse_for_keywords(title)

            if user and not db.lookup_ID(ID):
                log.debug("User found was: " + user)
                log.debug("Title is: " + title)
           
                try: 
                    reply_string = self.generate_reply_string(user)
                    self.reply(submission, reply_string)
                except praw.errors.InvalidComment:
                    log.warning("Submission was deleted")
                    pass

                db.insert(ID)

                # sleep to avoid rate limiting
                log.debug("Sleeping for 30 seconds to avoid being rate limited")
                time.sleep(30)

    def parse_for_keywords(self, title):
        # search for keyword string
        user = re.findall(r'by ([\w\s]*)',
                           str(title), re.IGNORECASE)
        try:
            # match will be None if we don't 
            # find the keyword string
            username = user[0]

        except IndexError:
            username = False

        return username

    def reply(self, submission, reply_string):
        
        log.debug("Posting in " + submission.title)
        
        try:
            submission.add_comment(reply_string)
            log.debug("Post sucessful!")

        except praw.errors.RateLimitExceeded as error:
            log.debug("Rate limit exceeded, must sleep for "
                      "{} mins".format(float(error.sleep_time / 60)))
            time.sleep(error.sleep_time)
            # try to reply to the comment again
            submission.add_comment(reply_string)
            log.debug("Reply sucessful!")

        except praw.errors.HTTPException as error:
            log.debug("HTTPError when posting. Sleeping for 10 seconds")
            log.debug(error)
            time.sleep(10)

    def generate_reply_string(self, user):
        reply_string = "Artist: [" + user.lower() + ".deviantart.com](" + user.lower() + ".deviantart.com)"
        return reply_string
 
###########################################################################
class Database:

    def __init__(self):
        # connect to and create DB if not created yet
        self.sql = sqlite3.connect('submissionIDs.db')
        self.cur = self.sql.cursor()

        self.cur.execute('CREATE TABLE IF NOT EXISTS submissions(ID TEXT)')
        self.sql.commit()

    def insert(self, ID):
        """
        Add ID to comment database so we know we already replied to it
        """
        self.cur.execute('INSERT INTO submissions (ID) VALUES (?)', [ID])
        self.sql.commit()

        log.debug("Inserted " + str(ID) + " into submissions database!")


    def lookup_ID(self, ID):
        """
        See if the ID has already been added to the database.
        """
        self.cur.execute('SELECT * FROM submissions WHERE ID=?', [ID])
        result = self.cur.fetchone()
        return result



##############################################################################
# Makes stdout and stderr print to the logging module
def config_logging():
    """ Configures the logging to external file """
    global log
    
    # set file logger
    rootLog = logging.getLogger('')
    rootLog.setLevel(logging.DEBUG)
    
    # make it so requests doesn't show up all the time in our output
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    # apparently on AWS-EC2 requests is used instead of urllib3
    # so we have to silence this again... oh well.
    logging.getLogger('requests').setLevel(logging.WARNING)

    # set format for output to file
    formatFile = logging.Formatter(fmt='%(asctime)-s %(levelname)-6s: '\
                                       '%(lineno)d : %(message)s',
                                   datefmt='%m-%d %H:%M')
    
    # add filehandler so once the filesize reaches 5MB a new file is 
    # created, up to 3 files
    fileHandle = logging.handlers.RotatingFileHandler("INFO.log",
                                                      maxBytes=5000000,
                                                      backupCount=5,
                                                      encoding = "utf-8")
    fileHandle.setFormatter(formatFile)
    rootLog.addHandler(fileHandle)
    
    # configures logging to console
    # set console logger
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG) #toggle console level output with this line
    
    # set format for console logger
    consoleFormat = logging.Formatter('%(levelname)-6s %(message)s')
    console.setFormatter(consoleFormat)
    
    # add handler to root logger so console && file are written to
    logging.getLogger('').addHandler(console)
    log = logging.getLogger('fakemon')
    stdout = LoggerWriter(log.debug)
    stderr = LoggerWriter(log.warning)

###############################################################################
class LoggerWriter:
    def __init__(self, level):
        self.level = level

    def write(self, message):
        # eliminate extra newlines in default sys.stdout
        if message != '\n':
            self.level(message)

    def flush(self):
        self.level(sys.stderr)


###############################################################################
def connect():
    log.debug("Logging in...")
    
    r = praw.Reddit("browser-based:Fakemon Moderator script:v0.2 (by /u/camerongagnon for /u/groovetonic)")
    
    config = ConfigParser()
    config.read("login.txt")
    
    username = config.get("Reddit", "username")
    password = config.get("Reddit", "password")
    
    r.login(username, password, disable_warning=True)
    
    return r


###############################################################################
def main():
    try:
        r = connect()
        while True:
            try:
                sub = Submissions("fakemon", r)
                sub.get_titles_to_parse()
                sub.post_title_comment()
                log.debug("Sleeping for 1 hour")
                time.sleep(3600)
        
            except (exceptions.HTTPError, exceptions.Timeout, exceptions.ConnectionError) as err:
                log.warning("HTTPError, sleeping for 10 seconds")
                log.warning(err)
                time.sleep(10)
                continue

    except KeyboardInterrupt:
        log.debug("Exiting")
        exit(0)


###############################################################################
#### MAIN ####
###############################################################################
if __name__ == '__main__':
    config_logging()
    main()
