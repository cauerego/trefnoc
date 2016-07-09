#!/usr/bin/python2.5

# for more about please look at the help below, run "./trefnoc.py -h" or visit http://cregox.com/trefnoc

import math, sys, os, subprocess, time # needed for the core
import re # could be skipped if a better method would be found to get the file's time
import MySQLdb, MySQLdb.cursors # only needed if queue is handled by a database
import hashlib # good for making uniqueness out of files named diferently
import logging, datetime # this is highly advised for diagnosing issues (to fix: logging is still not being used)
import smtplib # good for warning an admin (to fix: actually to be implemented)
from optparse import OptionParser, OptionGroup # used for parsing command line arguments
from PyQt4 import QtCore, QtGui # if you want a Graphical User Interface, that is (to fix: use more signals, but need to return values from them)

### below there are configurable options

# "static global variables"
args = {}
args['database_host'] = 'localhost'
args['database_user'] = 'user'
args['database_pass'] = 'pass'
args['database_tabl'] = 'videos'
args['database_alth'] = '' # alternate host
args['database_altu'] = '' # alternate host's user
args['database_altp'] = '' # alternate host's user's password
args['database_altt'] = '' # alternate host's table
args['database_alte'] = 'VZ_ALT_DATABASE_SERVER' # enviroment var which contains the alternate host

args['workingDirectory'] = 'uploads/' # default output path, if empty sets to current
args['frames_to_preview_on_thumbnail'] = 7
args['daemonInterval'] = (2*60)+56 # seconds
args['logFile'] = '/var/log/trefnoc.log'
args['ffmpeg'] = '/usr/bin/ffmpeg'
args['startInDaemon'] = False
args['verbose'] = False
args['quiet'] = False
args['debug'] = False


### program starts here

def help (version, parser):
	print 'TREfNOC - a utility for CONvERT-ing REf-erence files to a normalized standard'
	print version
	print ''
	print '  The idea here is automating the conversion and standardization of media files being uploaded to a server, to make them properly avaiable to the website.'
	print '  Videos will be converted to a default format, get thumbnails and its frames extracted for a quick mouse over preview.'
	print '  Images will just be made into JPEG.'
	print ''
	parser.print_help()
	print ''
	print 'more examples:'
	print ' $ trefnoc.py -dv'
	print ' (runs in debug and verbose modes, printing ffmpeg outputs as well but not logging them.)'
	print ' $ py -t20 -si 120 --log="/tmp/trefnoc.log"'
	print ' (set thumbnail frames to 20, daemon interval to 2 minutes and the log file.)'
	sys.exit()

def help_usage ():
	print 'usage: trefnoc.py [hfbgtilqvd]... [PATH]'
	print 'example: trefnoc.py -d'
	print "try `trefnoc.py --help' for more information and command line options."

def parseArguments ():
	version = 'version 1.0 built in 2010-05-14 - for more info, visit http://cregox.com/trefnoc'

	if len(sys.argv) < 2:
		help_usage()
		return False

	if len(args['workingDirectory']) > 0:
		if args['workingDirectory'][0] != '/':
			args['workingDirectory'] = '%s/%s'%(os.getcwd(), args['workingDirectory'])

	parser = OptionParser(
		usage='usage: trefnoc.py [OPTIONS]... [PATH]', version=version, add_help_option=False,
		description='PATH: where the files will be saved - if none is provided the current default one will be chosen: ' + args['workingDirectory'])
	parser.add_option('-h', '--help', dest='help', action='store_true', help='show this help message and exit')
	parser.add_option('-g', '--ffmpeg', dest='ffmpeg', type='string', default=args['ffmpeg'], help='determine the path of ffmpeg, needed for converting (%default)')
	parser.add_option('-t', '--frames', dest='frames', type='int', default=args['frames_to_preview_on_thumbnail'], help='select how many frames should be generated for the thumbnailed preview, use 0 to none (%default)')
	parser.add_option('-i', '--interval', dest='interval', type='int', default=args['daemonInterval'], help='how many seconds should the Daemon hold before re-running (%default)')
	parser.add_option('-s', '--daemon', dest='daemon', action='store_true', default=args['startInDaemon'], help='starts running daemon as soon as the program begins')

	outputGroup = OptionGroup(parser, 'Output handling')
	outputGroup.add_option('-l', '--log', dest='log', metavar="FILE", default=args['logFile'], help='use a different log file than the default (%default)')
	outputGroup.add_option('-q', '--quiet', dest='quiet', action='store_true', default=args['quiet'], help="doesn't display anything on screen, given no verbose or debug is set.")
	outputGroup.add_option('-v', '--verbose', dest='verbose', action='store_true', default=args['verbose'], help='print log information on screen. Overrides quiet.')
	outputGroup.add_option('-d', '--debug', dest='debug', action='store_true', default=args['debug'], help='set to log and display debugging information.')
	parser.add_option_group(outputGroup)

	(option, arg) = parser.parse_args(sys.argv)

	if len(arg) > 1:
		if len(arg[1]) > 0:
			if arg[1][0] != '/':
				args['workingDirectory'] = '%s/%s'%(os.getcwd(), arg[1])
			else:
				args['workingDirectory'] = arg[1]

	if option.help:
		help(version, parser)

	args['frames_to_preview_on_thumbnail'] = option.frames
	args['daemonInterval'] = option.interval
	args['logFile'] = option.log
	args['ffmpeg'] = option.ffmpeg
	args['verbose'] = option.verbose
	args['quiet'] = option.quiet
	args['debug'] = option.debug

	return (option, arg)

class Trefnoc (QtGui.QWidget):
	""" Trefnoc contains "global vars" as its attributes for internal use, read-only - never use global vars among threads """
	blockSize = 2**14 # for optimizing reading / opening big files, for md5 it must be multiple of 2**7, or 128
	totalSteps = 20 # must be manually set according to how many steps the progress bar will have.

class MainWindow (QtGui.QWidget):
	""" MainWindow contain GUI elements only """
	thread = None
	queueNumber = 0

	def __del__ (self):
		log('[info] treFnoc exited')
	def __init__ (self, parent = None):
		""" window constructor only """
		QtGui.QWidget.__init__(self, parent)

		self.setWindowTitle('treFnoc (Video Conversor)')

		self.thread = Worker() # this does not begin a thread - look at "Worker.run" for mor details
		self.connect(self.thread, QtCore.SIGNAL('finished()'), self.unfreezeUi)
		self.connect(self.thread, QtCore.SIGNAL('terminated()'), self.unfreezeUi)

		# Horizontal and Vertical boxes
		mainLayout = QtGui.QVBoxLayout()
		listsLayout = QtGui.QHBoxLayout()
		queueLayout = QtGui.QVBoxLayout()
		finishedLayout = QtGui.QVBoxLayout()
		buttonsLayout = QtGui.QHBoxLayout()

		self.listQueue = QtGui.QListWidget()
		self.listFinished = QtGui.QListWidget()

		# queues
		queueLayout.addWidget(QtGui.QLabel('Queue'))
		queueLayout.addWidget(self.listQueue)
		finishedLayout.addWidget(QtGui.QLabel('Finished'))
		finishedLayout.addWidget(self.listFinished)
		listsLayout.addLayout(queueLayout)
		listsLayout.addLayout(finishedLayout)
		self.connect(self.thread, QtCore.SIGNAL('addQueue(QString)'), self.addQueue)
		self.connect(self.thread, QtCore.SIGNAL('addFinished(QString)'), self.addFinished)

		# progress bar
		self.progress = QtGui.QProgressBar()
		self.progress.setTextVisible(True)
		self.progress.setFormat('%v / %m (%p%)')
		mainLayout.addLayout(listsLayout)
		mainLayout.addWidget(QtGui.QLabel('Progress'))
		mainLayout.addWidget(self.progress)
		self.connect(self.thread, QtCore.SIGNAL('setProgressRange(float, int, int, QString)'), self.setProgressRange)
		self.connect(self.thread, QtCore.SIGNAL('setProgress(float, int, QString)'), self.setProgress)

		# buttons
		self.buttonsLabel = QtGui.QLabel('select an action below')
		mainLayout.addWidget(self.buttonsLabel)

		self.buttonDaemon = QtGui.QPushButton('Daemon - converts every %s sec'% args['daemonInterval'])
		buttonsLayout.addWidget(self.buttonDaemon)
		self.connect(self.buttonDaemon, QtCore.SIGNAL('clicked()'), self.pressDaemon)

		self.buttonConvert = QtGui.QPushButton('Convert - Manually')
		buttonsLayout.addWidget(self.buttonConvert)
		self.connect(self.buttonConvert, QtCore.SIGNAL('clicked()'), self.convertOnce)

		mainLayout.addLayout(buttonsLayout)

		# show
		self.setLayout(mainLayout)
		if args['startInDaemon']:
			pressDaemon()

	def unfreezeUi (self, progressValue = None):
		self.buttonConvert.setEnabled(True)
		self.buttonDaemon.setEnabled(True)
		self.setProgressRange(msg='0')
		self.setProgress()

	def setProgressRange (self, delay = 0.0, min = 0, max = 1, msg = ''):
		self.progress.setRange(min, max)
		if msg == '0':
			self.buttonsLabel.setText('choose an action below')
		elif msg == '1':
			self.buttonsLabel.setText('running . . .')
		elif msg == '2':
			if delay > 0:
				self.buttonsLabel.setText('waiting %.1f seconds'%(args['daemonInterval'] - delay))
			else:
				self.buttonsLabel.setText('waiting')
		else:
			self.buttonsLabel.setText(msg)
		self.progress.reset()

	def setProgress (self, delay = 0.0, value = 0, msg = ''):
		self.progress.setValue(value)
		if msg != '':
			self.buttonsLabel.setText(msg)
		if delay > 0:
			self.buttonsLabel.setText('waiting %.1f seconds'%(args['daemonInterval'] - delay))

	def addQueue (self, value):
		self.queueNumber += 1
		self.listQueue.addItem(QtGui.QListWidgetItem('%d. %s'%(self.queueNumber, value)))

	def addFinished (self, value = '', itemN = 0):
		# the top most item (0) on the queue list should always be the first to go, as it will be numbered lower
		try:
			itemText = self.listQueue.item(itemN).text()
		except:
			log(bcolors.critical('[critical] addFinished must only be called after an addQueue - ' + str(sys.exc_info())))
			raise
		self.listFinished.addItem(QtGui.QListWidgetItem('%s %s'%(itemText, value)))
		self.listQueue.takeItem(itemN)

	def convertOnce (self):
		self.buttonConvert.setEnabled(False)
		self.buttonDaemon.setEnabled(False)
		self.thread.convert()

	def pressDaemon (self):
		self.buttonDaemon.setEnabled(False)
		if self.thread.isDaemonRunning():
			self.thread.setDaemonStopSignal(True)
			self.buttonDaemon.setText('Daemon - converts every %s sec'% args['daemonInterval'])
		else:
			self.buttonConvert.setEnabled(False)
			self.thread.startDaemon()
			self.buttonDaemon.setText('Stop Daemon')
			self.buttonDaemon.setEnabled(True)

class Worker (QtCore.QThread):
	""" Worker contains different threads that should run in the background, one per time in the same thread """
	fileName = None
	progressStep = 0
	daemonIsRunning = False
	daemonStopSignal = False
	daemonCurrentDelay = 0

	def isDaemonRunning (self): return self.daemonIsRunning
	def setDaemonStopSignal (self, bool): self.daemonStopSignal = bool

	def __init__ (self, parent = None):
		QtCore.QThread.__init__(self, parent)
		self.exiting = False
		self.thread_to_run = None  # which def will be running

	def __del__ (self):
		self.exiting = True
		self.thread_to_run = None
		self.wait()

	def run (self):
		""" Note: This is never called directly and accepts no argument. This begins the thread. """
		if self.thread_to_run != None:
			self.thread_to_run(mode='continue')

	def startDaemon (self, mode = 'run'):
		if mode == 'run':
			self.thread_to_run = self.startDaemon
			return self.start() # this will begin the thread

		self.daemonIsRunning = True
		self.daemonStopSignal = False
		sleepStep = 0.1 # don't know how to interrupt while sleeping - so the less sleepStep, the faster StopSignal will work

		# begins the daemon in an "infinite" loop
		while self.daemonStopSignal == False and not self.exiting:
			self.emit(QtCore.SIGNAL('setProgressRange(float, int, int, QString)'), self.daemonCurrentDelay, 0, Trefnoc.totalSteps, '1') # run
			self.convert('continue')
			self.emit(QtCore.SIGNAL('setProgressRange(float, int, int, QString)'), self.daemonCurrentDelay, 0, args['daemonInterval'] / sleepStep, '2') # wait
			self.daemonCurrentDelay = 0
			while self.daemonStopSignal == False and not self.exiting and self.daemonCurrentDelay < args['daemonInterval']:
				self.emit(QtCore.SIGNAL('setProgress(float, int, QString)'), self.daemonCurrentDelay, (self.daemonCurrentDelay+sleepStep)/sleepStep, '')
				time.sleep(sleepStep) # delay is actually set by while, but this holds for 1 second
				self.daemonCurrentDelay += sleepStep

		# daemon stopped, reseting everything
		self.daemonIsRunning = False
		self.daemonCurrentDelay = 0
		self.emit(QtCore.SIGNAL('terminated'))
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, 0)
		self.emit(QtCore.SIGNAL('setProgressRange(float, int, int, QString)'), self.daemonCurrentDelay, 0, 1, '0')

	def convert (self, mode = 'run'):
		if mode == 'run':
			self.thread_to_run = self.convert
			return self.start() # this will begin the thread

		self.progressStep = 0

		self.emit(QtCore.SIGNAL('setProgressRange(float, int, int, QString)'), self.daemonCurrentDelay, 0, Trefnoc.totalSteps, 'connecting the database. . .')

		# start connection with the database - the first one may take a while
		self.progressStep = 1
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
		dbConnection, dbCursor = connectDb()
		try:
			# grab from the database a list of files to be converted, should be as fast as possible
			self.progressStep += 1
			self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
			if args['debug']:
				if self.daemonCurrentDelay == 0:
					executeDb(dbCursor, 'UPDATE ref SET ref_status = 2 WHERE ref_id IN (77, 78, 79)') # setting status and ...
					executeDb(dbCursor, 'UPDATE ref SET ref_checksum = "" WHERE ref_id IN (77, 78, 79)') # removing checksum for debugging
			executeDb(dbCursor, 'SELECT COUNT(*) total FROM ref WHERE ref_status IN (1, 2)')  # 1 is for processing, 2 for downloaded and 3 for error
			row = dbCursor.fetchone()
			if row['total'] == 0:
				log(bcolors.info('[info] There is no file to process in the database'))
				return None
			else:
				log(bcolors.info('[info] Total number of files processing: ' + str(row['total'])))
			executeDb(dbCursor, 'SELECT * FROM ref WHERE ref_status IN (1, 2)')
		finally:
			closeDb(dbConnection) # always close database connections as soon as possible

		# iterate through all results to show on the queue
		if self.daemonIsRunning:
			startedMode = ''
		else:
			startedMode = '[modo manual] '
		self.emit(QtCore.SIGNAL('setProgress(float, int, QString)'), self.daemonCurrentDelay, self.progressStep, 'running . . .')
		for row in (dbCursor.fetchall()):  # there should never be many rows, they all must be normalized to status 0 or deleted
			# updating queue and log
			self.emit(QtCore.SIGNAL('addQueue(QString)'), '%s %s#%s'%
				(time.ctime(), startedMode, row['ref_path']) )

		#	dbConnection, dbCursor = connectDb(dbConnection)
		#	executeDb(dbCursor, 'SELECT * FROM ref WHERE ref_status IN (1, 2)')
		#	closeDb(dbConnection) # always close database connections as soon as possible
		dbCursor.scroll(0, 'absolute') # move back to first row
		for row in (dbCursor.fetchall()):
			if args['debug']: self.fileName = args['workingDirectory'] + 'file.mpg'
			self.fileName = row['ref_path']
			log(bcolors.info('[info] %s iniciando %s%s'%(time.ctime(), startedMode, self.fileName)))
			if args['debug']: log(bcolors.debug('[debug] row: "%s"'% row))

			# generate the checksum, check against the DB, update it and announce the beginning of the conversion
			self.progressStep += 1
			self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
			try:
				checksum = md5_from_file(self.fileName) # each checksum generation can take a while
			except:
				self.emit(QtCore.SIGNAL('addFinished(QString)'), 'critical file checksum! (%s)'% time.ctime())
				log(bcolors.critical('[critical] Unknow error trying to generate checksum' + str(sys.exc_info())))
				raise
			if checksum == False:
				dbConnection, dbCursor = connectDb(dbConnection)
				executeDb(dbCursor, 'UPDATE ref SET ref_status = 3 WHERE ref_id = "%s"'% row['ref_id'])
				closeDb(dbConnection)
				self.emit(QtCore.SIGNAL('addFinished(QString)'), 'erro arquivo! (%s)'% time.ctime())
				log(bcolors.error('''[error] Couldn't open file to generate checksum'''))
				continue # maybe it would be better to "raise" if it could be done without interrupting the process
			else:
				if args['debug']: log(bcolors.debug('[debug] checksum: "%s"'% checksum))

			# open another DB connection to verify the checksum and update its status
			self.progressStep += 1
			self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
			dbConnection, dbCursor = connectDb(dbConnection)
			try:
				executeDb(dbCursor, 'SELECT * FROM ref WHERE ref_checksum = "%s"'% checksum)
				if dbCursor.fetchone() != None: # the query for the checksum should be empty
					executeDb(dbCursor, 'UPDATE ref SET ref_status = 3 WHERE ref_id = "%s"'% row['ref_id'])
					self.emit(QtCore.SIGNAL('addFinished(QString)'), 'erro checksum! (%s)'% time.ctime())
					log(bcolors.warning('[warning] MD5 of this file already exists on the database, thus it must be duplicate'))
					continue # maybe it would be better to "raise" if it could be done without interrupting the process
				executeDb(dbCursor, 'UPDATE ref SET ref_status = 1 WHERE ref_id = "%s"'% row['ref_id'])
			finally: # close DB connection before starting conversion
				closeDb(dbConnection)

			self.progressStep += 1
			try:
				self.convert_core()
			except:
				self.progressStep = Trefnoc.totalSteps - 2
				self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
				dbConnection, dbCursor = connectDb(dbConnection)
				executeDb(dbCursor, 'UPDATE ref SET ref_status = 3 WHERE ref_id = "%s"'% row['ref_id'])
				closeDb(dbConnection)
				self.emit(QtCore.SIGNAL('addFinished(QString)'), 'erro %s! (%s)'%(str(sys.exc_info()[0]), time.ctime()))
				log(bcolors.critical('[critical] Could not begin conversion %s'% str(sys.exc_info())))
				raise
			self.progressStep = Trefnoc.totalSteps - 1
			self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
			# now need to open DB connection again, to update status
			dbConnection, dbCursor = connectDb(dbConnection)
			executeDb(dbCursor, 'UPDATE ref SET ref_status = 0, ref_checksum = "%s" WHERE ref_id = "%s"'
				% (checksum, row['ref_id']) ) # this is the expected non-debug
			closeDb(dbConnection)
			self.emit(QtCore.SIGNAL('addFinished(QString)'), 'terminado em: %s'% time.ctime())
			log(bcolors.info('[info] %s terminando %s%s'%(time.ctime(), startedMode, self.fileName)))
		self.progressStep = Trefnoc.totalSteps
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)

		self.emit(QtCore.SIGNAL('setProgressRange(float, int, int, QString)'), self.daemonCurrentDelay, 0, Trefnoc.totalSteps, '0')

	# this is where the conversion is actually done
	def convert_core (self):
		# get time duration using ffmpeg
		duration = -1
		self.progressStep = 10
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
		if args['debug']: log(bcolors.debug('[debug] fileName (step %d): "%s"'%(self.progressStep, self.fileName)))
		if os.path.exists(self.fileName):
			result = shell(args['ffmpeg'] + ' -i "'+self.fileName+'"')
			result = re.search('Duration: (\d+):(\d+):(\d+).(\d+)', result, re.M)
			if args['debug']: log(bcolors.debug('[debug] re result (step %d): "%s"'%(self.progressStep, result.groups())))
			durationArray = result.groups()
			if durationArray:
				duration = ((float(durationArray[0]) * 3600) +
					(float(durationArray[1]) * 60) +
					float(durationArray[2]) +
					(float(durationArray[3]) / 100) )
		else:
			# treat error
			log(bcolors.error('''[error] Couldn't find file ''' + self.fileName))

		if args['debug']: log(bcolors.debug('[debug] Duration found: ' + str(duration)))

		self.progressStep += 1
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
		# extract big thumbnail to show as default
		strDuration = str(duration / 2);
		cmd = (args['ffmpeg'] + ' -y -i "' + self.fileName + '" -deinterlace -an -r 1 -t 1 -ss ' + strDuration +
			' "' + self.fileName + '.preview.jpg"' )
		shell(cmd)

		self.progressStep += 1
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
		# extract frames to show on thumbnail rollover preview
		frame_rate = args['frames_to_preview_on_thumbnail'] / duration
		if frame_rate < 0.05:
			frame_rate = 0.05
		cmd = (args['ffmpeg'] + ' -y -i "' + self.fileName + '" -deinterlace -an -r ' + str(frame_rate) +
			' "' + self.fileName + '.rollover_%02d.jpg"' )
		shell(cmd)

		self.progressStep += 1
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
		# create a playable FLV file for streaming or playing embeded
		cmd = (args['ffmpeg'] + ' -i "' + self.fileName + '" -mbd rd -flags +4mv+aic -trellis 2 -cmp 2 -subcmp 2 -g 300' +
			' "' + self.fileName + '.flv"' )
		shell(cmd)

		self.progressStep += 1
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)
		# create a standard quality MOV file for download
		cmd = (args['ffmpeg'] + ' -i "' + self.fileName + '"' +
			' -acodec libfaac -ab 128kb -vcodec mpeg4 -b 1200kb -mbd 2 -flags +4mv -trellis 2 -aic 2 -cmp 2 -subcmp 2' +
			' -metadata original="' + self.fileName + '"' +
			' "' + self.fileName + '.mov"' )
		shell(cmd)

		self.progressStep += 1
		self.emit(QtCore.SIGNAL('setProgress(float, int)'), self.daemonCurrentDelay, self.progressStep)

def connectDb (dbConnection = None):
	""" connects to the database server, based on the environment variables - remember to always db.close() it as soon as possible """
	if dbConnection == None:
		log(bcolors.info('[info] connecting to primary database server: ' + args['database_host']))
	elif args['debug']: log(bcolors.debug('[debug] connecting to primary database server: ' + args['database_host']))
	try:
		dbConnection = MySQLdb.connect(host=args['database_host'], user=args['database_user'], passwd=args['database_pass'], db=args['database_tabl'], cursorclass=MySQLdb.cursors.DictCursor)#, autocommit=True)
	except:
		args['database_alth'] = os.environ.get(args['database_alte'])
		if dbConnection == None:
			log(bcolors.info('[info] connecting to secondary database server: ' + str(args['database_alth'])))
		elif args['debug']: log(bcolors.debug('[debug] connecting to secondary database server: ' + str(args['database_alth'])))
		try:
			dbConnection = MySQLdb.connect(host=args['database_alth'], user=args['database_altu'], passwd=args['database_altp'], db=args['database_altt'])
		except:
			log(bcolors.critical('[critical] Could not connect to database server! ' + str(sys.exc_info())))
			raise
	if args['debug']: log(bcolors.debug('[debug] database connected!'))
	return dbConnection, dbConnection.cursor()

def executeDb (dbCursor = None, query = None):
	try:
		result = dbCursor.execute(query)
	except:
		log(bcolors.critical('[critical] Could not execute database query! - ' + str(sys.exc_info())))
		raise
	if args['debug']: log(bcolors.debug('[debug] query executed successfully: "%s"'% query))
	return result

def closeDb (dbConnection = None):
	try:
		dbConnection.close()
	except:
		log(bcolors.critical('[critical] Could not close the database server! - ' + str(sys.exc_info())))
		raise
	if args['debug']: log(bcolors.debug('[debug] database connection was successfully closed.'))
	return True

def md5_from_file (fileName, block_size=Trefnoc.blockSize):
	md5 = hashlib.md5()
	try:
		f = open(fileName)
	except:
		return False
	while True:
		data = f.read(block_size)
		if not data:
			break
		md5.update(data)
	f.close()
	return md5.hexdigest()

def shell (cmd):
	if args['debug']:
		doTime = 'time '
	else:
		doTime = ''
	process = subprocess.Popen(
		doTime + cmd + ' 2>&1', cwd=args['workingDirectory'],
		bufsize=0, shell=True, close_fds=True,
		stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
	# wait process to finish and gather [stdout, stderr]
	result = process.communicate()[0]
	if args['verbose']: print result
	return result

class bcolors ():
	CRITICAL = '\033[95m' #pink (50)
	ERROR = '\033[91m' #red (40)
	WARNING = '\033[93m' #yellow (30)
	INFO = '\033[94m' #blue (20)
	DEBUG = '\033[92m' #green (10)
	ENDC = '\033[0m' #must always go in the end, to return to default color
	def critical (self, text = ''): return self.CRITICAL + text + self.ENDC
	def error (self, text = ''): return self.ERROR + text + self.ENDC
	def warning (self, text = ''): return self.WARNING + text + self.ENDC
	def info (self, text = ''): return self.INFO + text + self.ENDC
	def debug (self, text = ''): return self.DEBUG + text + self.ENDC

def now (): return datetime.datetime.today()
def now_intl (): return str(now().strftime('%Y-%m-%d %H:%M:%S'))
def do_print (x): print x
def log (text, display='', call_print=do_print):
	msg = now_intl() + ' TREfNOC: ' + text
	if args['debug']: display = ''
	if display != None:
		call_print(msg + display)
	file = open(args['logFile'], 'a')
	file.write(msg + '\n')
	file.close()
	return msg

if __name__ == '__main__':
	log('Executing ' + os.path.abspath( __file__ ), display=None)
	bcolors = bcolors()
	parseArguments()
	log('Arguments provided: ' + str(sys.argv))
	log('Arguments being used: ' + str(args), display=None)
	log('[info] starting treFnoc . . .')
	app = QtGui.QApplication(sys.argv)
	win = MainWindow()
	win.show()
	log(bcolors.info('[info] window displayed'))
	sys.exit(app.exec_())
