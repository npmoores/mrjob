# Copyright 2009-2010 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Audit EMR usage over the past 2 weeks, sorted by job flow name and user.
"""
from __future__ import with_statement

import boto.utils
from collections import defaultdict
import datetime
import logging
import re
from optparse import OptionParser

from mrjob.emr import EMRJobRunner, describe_all_job_flows
from mrjob.util import log_to_stream

log = logging.getLogger('mrjob.tools.emr.audit_emr_usage')

JOB_FLOW_NAME_RE = re.compile(r'^(.*)\.(.*)\.(\d+)\.(\d+)\.(\d+)$')

def main():
    # parser command-line args
    option_parser = make_option_parser()
    options, args = option_parser.parse_args()

    if args:
        option_parser.error('takes no arguments')

    # set up logging
    if not options.quiet:
        log_to_stream(name='mrjob', debug=options.verbose)
    # suppress No handlers could be found for logger "boto" message
    log_to_stream(name='boto', level=logging.CRITICAL)

    print_report(options)

def make_option_parser():
    usage = '%prog [options]'
    description = 'Print a report on emr usage over the past 2 weeks.'
    option_parser = OptionParser(usage=usage, description=description)
    option_parser.add_option(
            '-v', '--verbose', dest='verbose', default=False,
            action='store_true',
            help='print more messages to stderr')
    option_parser.add_option(
            '-q', '--quiet', dest='quiet', default=False,
            action='store_true',
            help='just print job flow ID to stdout')
    option_parser.add_option(
            '-c', '--conf-path', dest='conf_path', default=None,
            help='Path to alternate mrjob.conf file to read from')
    option_parser.add_option(
            '--no-conf', dest='conf_path', action='store_false',
            help="Don't load mrjob.conf even if it's available")

    return option_parser

def print_report(options):

    emr_conn = EMRJobRunner(conf_path=options.conf_path).make_emr_conn()
    
    log.info(
        'getting info about all job flows (this goes back about 2 months)')
    now = datetime.datetime.utcnow()
    job_flows = describe_all_job_flows(emr_conn)

    job_flow_infos = []
    for jf in job_flows:
        job_flow_info = {}

        job_flow_info['id'] = jf.jobflowid

        job_flow_info['name'] = jf.name

        job_flow_info['created'] = datetime.datetime.strptime(
            jf.creationdatetime, boto.utils.ISO8601)

        # this looks to be an integer, but let's protect against
        # future changes
        job_flow_info['hours'] = float(jf.normalizedinstancehours)

        # split out mr job name and user
        # jobs flows created by MRJob have names like:
        # mr_word_freq_count.dave.20101103.121249.638552
        match = JOB_FLOW_NAME_RE.match(jf.name)
        if match:
            job_flow_info['mr_job_name'] = match.group(1)
            job_flow_info['user'] = match.group(2)
        else:
            # not run by mrjob
            job_flow_info['mr_job_name'] = None
            job_flow_info['user'] = None

        job_flow_infos.append(job_flow_info)

    if not job_flow_infos:
        print 'No job flows created in the past two months!'
        return

    earliest = min(info['created'] for info in job_flow_infos)
    latest = max(info['created'] for info in job_flow_infos)

    print 'Total # of Job Flows: %d' % len(job_flow_infos)
    print

    print 'All times are in UTC'
    print

    # Techincally, I should be using ISO8601 time format here, but it's
    # ugly and hard to read.
    ISOISH_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
    print 'Min create time: %s' % (
        earliest.strftime(ISOISH_TIME_FORMAT))
    print 'Max create time: %s' % (
        latest.strftime(ISOISH_TIME_FORMAT))
    print '   Current time: %s' % (
        now.strftime(ISOISH_TIME_FORMAT))
    print

    print 'All usage is measured in Normalized Instance Hours, which are'
    print 'roughly equivalent to running an m1.small instance for an hour'
    print

    # total compute-unit hours used
    total_hours = sum(info['hours'] for info in job_flow_infos)
    print 'Total Usage: %d' % total_hours
    print
    
    def fmt(mr_job_name_or_user):
        if mr_job_name_or_user:
            return mr_job_name_or_user
        else:
            return '(not started by mrjob)'

    # Top jobs
    print 'Top jobs (based on which job started the job flow):'
    mr_job_name_to_hours = defaultdict(float)
    for info in job_flow_infos:
        mr_job_name_to_hours[info['mr_job_name']] += info['hours']
    for mr_job_name, hours in sorted(mr_job_name_to_hours.iteritems(),
                                     key=lambda (n, h): (-h, n)):
        print '  %5d %s' % (hours, fmt(mr_job_name))
    print

    # Top users
    print 'Top users (based on which user started the job flow):'
    user_to_hours = defaultdict(float)
    for info in job_flow_infos:
        user_to_hours[info['user']] += info['hours']
    for user, hours in sorted(user_to_hours.iteritems(),
                              key=lambda (n, h): (-h, n)):
        print '  %5d %s' % (hours, fmt(user))
    print
    
    # Top job flows
    print 'Top job flows:'
    top_job_flows = sorted(job_flow_infos,
                           key=lambda i: (-i['hours'], i['name']))
    for info in top_job_flows:
        print '  %5d %-15s %s' % (info['hours'], info['id'], info['name'])
    print

if __name__ == '__main__':
    main()

    
