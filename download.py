'''

python download.py <url of file>

'''

from __future__ import division
import os,sys,threading,requests,shutil,base64,random,time
from urlparse import urlsplit
from urlparse import urlparse

# A thread should download not more than ~19 MB or 20000000 B
maxChunkSize = 20000000
# Where to download the file, currently it does it in the Present working directory
downloadDirectory = os.getcwd() + "/"
# Maximum simultaneous download threads for a file
maxDownloadThreads = 5

'''
  The threaded downloader class. Responsible for downloading chunks of a file of size <= maxChunkSize
'''
class Downloader(threading.Thread):
  
  def __init__(self,fileName,url,startByte,endByte,callback,statusReporter):
    threading.Thread.__init__(self)
    self.__fileName = fileName
    self.__url = url
    self.__startByte = startByte
    self.__endByte = endByte
    self._ERROR = False
    self.__callback = callback
    self.__statusReporter = statusReporter
    self._tries = 0
    self._allowedTries = 5
    self.__bytesDownloaded = 0
    self.__lastTime = int(time.time())

  def run(self):
    self.download()

  def download(self):
    self._ERROR = False
    self._tries += 1

    '''
      If the host does not support multiple connections per download, use a single one
    '''
    try:
      if self.__startByte == 0 and self.__endByte == 0:
        r = requests.get(self.__url, stream = True, allow_redirects=True)
      else:
        r = requests.get(self.__url, headers={"Range": "bytes=" + str(self.__startByte) + "-" + str(self.__endByte)}, stream = True, allow_redirects=True)
    except:
      self._ERROR = True
      self.__callback(self)
      return

    if r.status_code >=200 and r.status_code < 300:
      try:
        with open(downloadDirectory + self.__fileName, 'w+') as f:
          for chunk in r.iter_content(chunk_size=1024):
            # filter out keep-alive new chunks
            if chunk:
              f.write(chunk)
              f.flush()
              os.fsync(f)
              self.__bytesDownloaded += len(chunk)
              if (int(time.time())) - 1 >= self.__lastTime:
                self.__statusReporter(self.__bytesDownloaded)
                self.__bytesDownloaded = 0
              self.__lastTime = (int(time.time()))

          # Report progress before exiting
          self.__statusReporter(self.__bytesDownloaded)
          self.__bytesDownloaded = 0
          self.__lastTime = (int(time.time()))

          f.close()
      except:
        self._ERROR = True
        self.__callback(self)
        return
    else:
      self._ERROR = True
    # When finished downloading, callback the _threadHandler in UrlHandler
    self.__callback(self)
    return

class UrlHandler:

  def __init__(self,url):
    self.__url = url
    self.__size = 0
    self.__timesToRun = 1
    self.__runningThreads = 0
    self.__timesRun = 0
    self.__ERROR = False
    self.__downloadedBytes = 0
    self.__lastTime = int(time.time())
    self.__charsToDelete = 0
    self.__progress = 0

  '''
    Get name of the file from URL.
  '''
  def __url2name(self,url):
    if not filter(None,os.path.basename(urlsplit(url)[2])):
      return base64.urlsafe_b64encode('{uri.scheme}://{uri.netloc}/'.format(uri=urlparse(url)))
    else:
      return os.path.basename(urlsplit(url)[2])

  def __printProgress(self):
    if int(self.__size) > 0:
      try:
        self.__progress = ("%.2f" % ((int(self.__downloadedBytes) / int(self.__size)) * 100))
        txt = "Download Progress: "
        for i in range(0,self.__charsToDelete):
          print "\r",
        self.__charsToDelete = len(str(self.__progress)) + len(txt) + 1
        print txt + str(self.__progress) + "%",
        sys.stdout.flush()
      except Exception, e:
        print "Couldn't do it: %s" % e

  def _statusReporter(self,addedBytes):
    lock = threading.Lock()
    while True:
      if not lock.acquire(False):
        pass
      else:
        break
    prevTime = 0
    try:
      self.__downloadedBytes += addedBytes
      prevTime = self.__lastTime
      self.__lastTime = int(time.time())
    finally:
      if prevTime + 1 <= self.__lastTime:
        self.__printProgress()
      lock.release()

  '''
    Handle Callbacks from threads of Downloader and create new threads or retry previous ones if they failed
  '''
  def _threadHandler(self,callbackThread):
    # Lock resources till new thread is created or parts are combined
    lock = threading.Lock()
    while True:
      if not lock.acquire(False):
        pass
      else:
        break
    try:
      if callbackThread._ERROR == True:
        if callbackThread._tries < callbackThread._allowedTries:
          callbackThread.download()
        else:
          self.__ERROR = True
      else:
        # Increment thye number of successfully downloaded chunks
        self.__timesRun += 1
        # If all chunks have been downloaded, prooceed to combine them
        if self.__timesToRun == self.__timesRun:
          self.__makeFile()
        else:
          '''
            Create threads for new chunks, if required [At a time only, a maximum of maxDownloadThreads no.
            of threads will be running]
          '''
          if self.__runningThreads < self.__timesToRun:
            self.__makeDownloadThread()
    finally:
      lock.release()
      return

  def __makeFile(self):
    if self.__timesToRun == 1:
      if self.__ERROR == True:
        print "Error in downloading file."
      else:
        print "File download successful. Filename: " + self.__fileName
    else:
      if self.__ERROR == True:
        print "Error in downloading file."
      else:
        try:
          # Combine all file parts
          path = self.__getPath(downloadDirectory + self.__fileName)
          destination = open(path, 'a+')
          for l in range(0,self.__timesToRun):
            shutil.copyfileobj(open(downloadDirectory + self.__fileName + ".part" + str(l), 'rb'), destination)
            os.remove(downloadDirectory + self.__fileName + ".part" + str(l))
          destination.close()
          
          self.__printProgress()

          print "\nFile download successful. Details:\n-----------------------------------------------\n"
          print "File size: " + self.__size + " Bytes."
          print "Location: " + path + "\n"
        except:
          print "Download successful. Error in combining file parts."
          return
    return

  def __makeDownloadThread(self):
    if self.__runningThreads > 0:
      startByte = self.__runningThreads * maxChunkSize + 1
      endByte = startByte + maxChunkSize - 1
    else:
      startByte = 0
      endByte = startByte + maxChunkSize
    Downloader(self.__fileName + ".part" + str(self.__runningThreads),self.__url,startByte,endByte,self._threadHandler,self._statusReporter).start()
    self.__runningThreads += 1

  '''
    If a file with the same name exists, don't over write it
  '''
  def __getPath(self, fName):
    path = fName
    while True:
      if os.path.isfile(path):
        arr = path.split(".")
        if len(arr) > 1:
          ext = arr[len(arr)-1]
          arr[len(arr)-1] = str(random.randint(1, 10))
          arr.append(ext)
          path = ".".join(arr)
        else:
          path = path + str(random.randint(1, 10))
      else:
        break
    return path

  def download(self):
    self.__fileName = self.__url2name(self.__url)

    try:
      r = requests.head(self.__url, allow_redirects=True)
    except:
      print "Error fetching file details."
      return

    if r.status_code >=200 and r.status_code < 300:

      # Get size of file
      if 'content-length' in r.headers:
        self.__size = r.headers['content-length']
      else:
        self.__size = 0

      # Try to aquire the best possible file name available
      if 'content-disposition' in r.headers:
        # If the response has Content-Disposition, we take file name from it
        self.__fileName = r.headers['content-disposition'].split('filename=')[1]
        if self.__fileName[0] == '"' or self.__fileName[0] == "'":
          self.__fileName = self.__fileName[1:-1]
        elif r.url != self.__url:
          # if we were redirected, the real file name we take from the final URL
          self.__fileName = self.__url2name(r.url)

      # If a content-range header is present, partial retrieval worked.
      if self.__size > 0 and ("accept-ranges" in r.headers or "content-range" in r.headers) and self.__size > maxChunkSize:

        # Calculate number of chunks of the file
        if int(int(int(self.__size) / maxChunkSize) * maxChunkSize) < self.__size:
          self.__timesToRun = int(int(self.__size) / maxChunkSize) + 1
        else:
          self.__timesToRun = int(int(self.__size) / maxChunkSize)

        timesToRun = self.__timesToRun

        if self.__timesToRun >= maxDownloadThreads:
          timesToRun = maxDownloadThreads

        # Create maxDownloadThreads or __timesToRun number of threads for parallel downloading. (Whichever is less)
        for i in range(0,timesToRun):
          self.__makeDownloadThread()

      else:
        '''
          Download using a single thread.
          Possible causes: No available content length, parallel downloads not supported.
        '''
        # Handle file name already present exception [Do not over write]
        self.__fileName = self.__getPath(downloadDirectory + self.__fileName).split("/")[-1]
        thread = Downloader(self.__fileName,self.__url,0,0,self._threadHandler,self._statusReporter)
        thread.start()

      return
    else:
      # File could not be retrieved [Response headers]
      print "Error in downloading file. Error code: " + str(r.status_code)
      return

    return

if __name__ == '__main__':
  '''
    # Use if you want to clear the whole screen at once (Windows part untested, baah). Also, UNINDENT.
    # Windows
    if sys.platform.startswith('win'):
      os.system('cls')
    else: # Linux
      os.system('clear')
  '''
  # Clear some space for long URLs. No cluttered screen.
  print "\n"
  if len(sys.argv) < 2:
    print "Usage:\npython <script name> <url of file>"
  else:
    print "URL to download: " + sys.argv[1] + "\n"
    UrlHandler(sys.argv[1]).download()
  
  sys.exit()
