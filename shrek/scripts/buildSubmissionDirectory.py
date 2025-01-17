#!/usr/bin/env python 

import yaml
import argparse
import pydot
import os
import stat
import pathlib
import shutil
import glob
import sh
import networkx as nx

from shrek.scripts.buildJobScript import buildJobScript
from shrek.scripts.buildCommonWorklow import buildCommonWorkflow

from shrek.scripts.simpleLogger import DEBUG, INFO, WARN, ERROR, CRITICAL

def get_umask():
    umask = os.umask(0)
    os.umask(umask)
    return umask

def chmod_plus_x(path):
    os.chmod(
        path,
        os.stat(path).st_mode |
        (
            (
                stat.S_IXUSR |
                stat.S_IXGRP |
                stat.S_IXOTH
            )
        & ~get_umask()
        )
        )

   
def jobDirectoryName( tag, opts ):
    limit  = opts['maxSubmit']
    prefix = opts['submissionPrefix']
    # Make sure the prefix directory exists
    if ( not os.path.exists( prefix ) ):
        os.mkdir( prefix )

    # Submission directory
    subdir = "%s/%s"%(prefix,tag)

    yield subdir

def buildSubmissionDirectory( tag, jdfs_, site, args, opts, glvars ):

    # Make certain we have absolute path to job definition files
    jdfs = []
    for jdf in jdfs_:
        jdfs.append( os.path.abspath( jdf ) )

    # 
    subdir = ""
    for s in jobDirectoryName( tag, opts ):

        if os.path.exists( s ):

            # Submission directory should be on the requested branch
            sh.git.checkout ( args.branch,                          _cwd=s )                        

            WARN('Existing submission directory %s is cleared'%s)
            shutil.rmtree( s )
                
        subdir = s            
        os.mkdir( subdir )
        INFO('PanDA submission directory %s'%s)            
        break

    # Copy plugins
    if os.path.exists( './plugins/' ):
        sh.cp( '-r', './plugins', subdir )        

    # Copy job description files to staging area
    for j in jdfs:
        INFO('Copy %s to submission directory %s'%(j,subdir))                    
        sh.cp( j, subdir )

    # Build job scripts and stage into directory
    input_jobs = []
    job_scripts = []
    jobs = []
    for jdf in jdfs:
        stem = pathlib.Path(jdf).stem        
        (job, script) = buildJobScript( jdf, tag, opts, glvars )
        jobs.append(job)

        # A job w/ no name will be treated as pure input
        if job.parameters:
            name = job.parameters.name
        else:
            input_jobs.append( job )
            continue

        assert(script)
        assert(job)

        job_scripts.append( name + ".sh" )

        with open( subdir + '/' + name + '.sh', 'w' ) as f:
            f.write('#!/usr/bin/env bash\n\n')
            if len(job.resources):            
                f.write('# Stage resources into working directory\n')
                f.write('cp -R __%s/* .\n'%name)
            f.write("# ... start of the user script ................................................\n")
            f.write(script)
            f.write("# ... end of the user script   ................................................\n")

        # Make script executable
        chmod_plus_x(subdir + '/' + name + '.sh') 


        # Create a subdirectory for job resources
        job_resources = []
        if len(job.resources):
                        
            jobdir = subdir + '/__' + name
            os.mkdir( jobdir )

            for r in job.resources:
                if r.type=='file':
                    INFO("Linking %s --> %s"%(r.url,jobdir))
                    myurl = os.path.expanduser( os.path.expandvars( r.url ) )
                    myurl = glvars.get( myurl, myurl ) # Command line substitution
                    for f in glob.glob(myurl):
                        head,tail = os.path.split( f )
                        os.symlink( os.path.abspath(f), jobdir + '/' + tail )
                        job_resources.append( os.path.abspath(f) )

    # Copy pfnLists to submission directory (if any)
    for job in jobs:

        # Job specifies a pfnList
        if hasattr( job.parameters, "pfnList" ):
        
            # Try global substitution for the pfnlist name.  If there is no substitution
            # registered, use the value provided in the parameter block
            pfnList = glvars.get(job.parameters.pfnList,job.parameters.pfnList) 

            # Copy the content files to the submission directory
            pfnOut = ""
            with open( pfnList, 'r' ) as myfile:
                for pfn in myfile:
                    sh.cp( pfn.strip(), subdir )
                    pfnOut+=os.path.basename(pfn)
            with open( subdir+'/'+os.path.basename(pfnList),'w' ) as of:
                of.write(pfnOut)
                

                

    # Build CWL for PanDA submission
    ( cwf, yml, dgr ) = buildCommonWorkflow( jdfs, tag, site, args, glvars )
    cwlfile = '%s-workflow.cwl'%tag
    ymlfile = '%s-input.yaml'%tag
    # Output common workflow
    with open( subdir + '/' + cwlfile, 'w') as f:
        f.write( cwf )
    # Output inputs into the yaml file
    with open( subdir + '/' + ymlfile, 'w') as f:
        f.write( yml )
        f.write('\n')
        for job in input_jobs:
            for inp in job.inputs:
                f.write('# %s %s %s\n'%(job.name,inp.name,inp.datasets))
                f.write('%s: %s\n'%(inp.name,inp.datasets))


    # Create PNG from the digraph and store in the staging area along
    # with a markdown file for display purposes
    if dgr and args.diagram:
        dot = nx.drawing.nx_pydot.to_pydot(dgr)
        dot.write_png( "%s/workflow.png"%subdir )

    # Add all artefacts to the git repo
    message = '[Shrek submission tag %s]'%tag
    sh.git.add    ( '*', _cwd=subdir )
    try:
        sh.git.commit ( '-m %s'%message,     _cwd=subdir )
    except sh.ErrorReturnCode_1:
        print("WARN: probably trying to submit duplicate code")
    except sh.ErrorReturnCode:
        print("WARN: unknown error during git commit ")


    # Markdown documentation for this job...
    with open("%s/README.md"%subdir,"w") as md:
        md.write( "## SHREK Inputs\n")
        for j in jdfs:
            md.write( "- %s\n"%j )
        md.write("## Generated scripts\n") # ... unclear input job vs normal ...
        for s in job_scripts:
            md.write("- %s\n"%s )
        md.write("## Job resources\n")
        for r in job_resources:
            md.write("- %s\n"%r)
        if 0==len(job_resources):
            md.write("- none\n")

        md.write( "## Job dependencies\n" )
        md.write( "![Workflow graph](workflow.png)\n" )

        for job in jobs:
            md.write("- %s\n"%job.name )
            if len(job.inputs) > 0:
                md.write("  inputs:\n" )
            for i in job.inputs:
                md.write( "  - %s\n"%i.name )
            md.write("\n  outputs:\n" )
            for o in job.outputs:
                md.write( "  - %s\n"%o.name )
            


        md.write( "## PanDA Monitoring\n" )
        taskname = ''
        if args.group == "":
            taskname = 'user.%s.%s'%(args.user,opts['taguuid'])
        else:
            taskname = 'group.%s.%s'%(args.group,opts['taguuid'])

        if len(jobs)==1:      # prun tasks taskname url takes a trailing /
            taskname += "/"
        else:
            taskname += "_*"  # pchain tasks taskname url is a wildcard
        
        md.write( "[panda monitoring](https://sphenix-panda.apps.rcf.bnl.gov/tasks/?taskname=%s)\n"%taskname )

    # Print the monitoring link
    WARN( "==========================================================")
    WARN( "Workflow monitoring https://sphenix-panda.apps.rcf.bnl.gov/tasks/?taskname=%s\n"%taskname )        
    WARN( "==========================================================")

                        
    return (subdir,cwlfile,ymlfile,jobs)
        
def main():

    parser = argparse.ArgumentParser(description='Build job submission area')
    parser.add_argument('yaml', metavar='YAML', type=str, nargs="+",
                                        help='input filename')
    parser.add_argument('--tag',  type=str, help='production tag' )
    parser.set_defaults(submit=False)

    args = parser.parse_args()

    buildSubmissionDirectory( args.tag, args.yaml )

if __name__ == '__main__':
    main()    
                    
    
