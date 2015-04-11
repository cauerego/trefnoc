The goal is gathering a list of files being uploaded to the company's intranet that will work as media reference, and normalize them to the same standard which will be utilized on the website.

This is a heavy process so it must run on a separate server and be easy to diagnose issues, if any happen. So there comes trefnoc.

I hope this can serve as reference for people looking on how to do some stuff on Python. Features include:
- multithreaded and very simplistic Graphical User Interface, with a progress bar and queue lists.
- command line options, using parser
- database connection
- proper error handling
- log to screen and to file
- hashing file to MD5 (not SHA1 due to company standards)
- and little more