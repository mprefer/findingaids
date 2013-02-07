# file findingaids/fa_admin/tests.py
#
#   Copyright 2012 Emory University Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import cStringIO
import logging
from mock import patch
import os
import re
from shutil import rmtree, copyfile
import sys
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.urlresolvers import reverse

from eulexistdb.db import ExistDB, ExistDBException
from eulexistdb.testutil import TestCase
from eulxml.xmlmap.core import load_xmlobject_from_file
from eulxml.xmlmap.eadmap import EAD_NAMESPACE

from findingaids.fa.models import FindingAid
from findingaids.fa.urls import TITLE_LETTERS
from findingaids.fa_admin import tasks, utils
from findingaids.fa_admin.management.commands import prep_ead as prep_ead_cmd
from findingaids.fa_admin.management.commands import unitid_identifier
from findingaids.fa_admin.mocks import MockDjangoPidmanClient  # MockHttplib unused?


# unit tests for utils, manage commands, etc

### unit tests for findingaids.fa_admin.utils

class UtilsTest(TestCase):
    db = ExistDB()

    def setUp(self):
        # temporarily replace pid client with mock for testing
        self._django_pid_client = utils.DjangoPidmanRestClient
        utils.DjangoPidmanRestClient = MockDjangoPidmanClient

        # save pid config settings to restore in teardown
        self._pid_config = {
            'PIDMAN_HOST': settings.PIDMAN_HOST,
            'PIDMAN_USER': settings.PIDMAN_USER,
            'PIDMAN_PASSWORD': settings.PIDMAN_PASSWORD,
            'PIDMAN_DOMAIN': settings.PIDMAN_DOMAIN
            }

        # initialize valid and invalid ead fixtures
        self.valid_eadfile = os.path.join(settings.BASE_DIR, 'fa_admin',
            'fixtures', 'hartsfield558.xml')
        self.valid_ead = load_xmlobject_from_file(self.valid_eadfile, FindingAid)

        self.invalid_eadfile = os.path.join(settings.BASE_DIR, 'fa_admin',
            'fixtures', 'hartsfield558_invalid.xml')
        self.invalid_ead = load_xmlobject_from_file(self.invalid_eadfile, FindingAid)

    def tearDown(self):
        # ensure test file gets removed even if tests fail
        try:
            self.db.removeDocument(settings.EXISTDB_TEST_COLLECTION + '/hartsfield_other.xml')
        except ExistDBException:
            # not an error if this fails - not used by every test
            pass

        MockDjangoPidmanClient.search_result = MockDjangoPidmanClient.search_result_nomatches
        # restore non-mock client
        utils.DjangoPidmanRestClient = self._django_pid_client
        # restore pid config settings
        for key, val in self._pid_config.iteritems():
            setattr(settings, key, val)

    def test_check_ead(self):
        # check valid EAD - no errors  -- good fixture, should pass all tests
        dbpath = settings.EXISTDB_TEST_COLLECTION + '/hartsfield558.xml'
        errors = utils.check_ead(self.valid_eadfile, dbpath)
        self.assertEqual(0, len(errors))

        # should cause several errors - not schema valid, eadid, series/subseries ids missing, index id missing
        errors = utils.check_ead(self.invalid_eadfile, dbpath)
        self.assertNotEqual(0, len(errors))
        self.assert_("attribute 'invalid': The attribute 'invalid' is not allowed"
                     in errors[0])   # validation error message

        # NOTE: somewhere between lxml 2.3.1 and 3.0.1 we started getting
        # duplicate validation errors. work around it for now.
        # (errors seem to be aggregating instead of clearing out....)
        while errors[0] == errors[1]:
            errors.pop(0)
        self.assert_("Line 2" in errors[0], "validation error includes line number")   # validation error message
        self.assert_("eadid 'hartsfield558.xml' does not match expected value" in errors[1])
        self.assert_("series c01 id attribute is not set for Series 1" in errors[2])
        self.assert_("subseries c02 id attribute is not set for Subseries 6.1" in errors[3])
        self.assert_("index id attribute is not set for Index of Selected Correspondents" in errors[4])

        # eadid uniqueness check in eXist
        self.db.load(open(self.valid_eadfile), dbpath, True)
        errors = utils.check_ead(self.valid_eadfile, dbpath)
        # same eadid, but present in the file that will be updated - no errors
        self.assertEqual(0, len(errors))

        # upload same file to a different path - non-unique eadid error
        self.db.load(open(self.valid_eadfile), settings.EXISTDB_TEST_COLLECTION + '/hartsfield_other.xml', True)
        errors = utils.check_ead(self.valid_eadfile, dbpath)
        self.assertEqual(1, len(errors))
        self.assert_("Database already contains 2 instances of eadid" in errors[0])

        # remove version with correct path to test single conflicting eadid
        self.db.removeDocument(dbpath)
        errors = utils.check_ead(self.valid_eadfile, dbpath)
        self.assertEqual(1, len(errors))
        self.assert_("Database contains eadid 'hartsfield558' in a different document" in errors[0])

    def test_check_eadxml(self):
        # use invalid ead fixture to check error detection
        ead = self.invalid_ead
        ead.eadid.value = 'foo#~@/'    # set invalid eadid for this test only

        # invalid fixture has several errors
        errors = utils.check_eadxml(ead)
        self.assertNotEqual(0, len(errors))
        # - series/subseries ids missing, index id missing
        self.assert_("series c01 id attribute is not set for Series 1: Personal papers, 1918-1986"
                    in errors, 'c01 missing id error reported')
        self.assert_("subseries c02 id attribute is not set for Subseries 6.1: Minerals and mining files, 1929-1970"
                    in errors, 'c02 missing id error reported')
        self.assert_("index id attribute is not set for Index of Selected Correspondents"
                    in errors, 'index missing id error reported')
        # - origination count error
        self.assert_("Site expects only one archdesc/did/origination; found 2" in errors,
                    'multiple origination error reported')
        # - whitespace in list title
        self.assert_("Found leading whitespace in list title field (origination/persname): " +
                    "'  Hartsfield, William Berry.'" in errors, 'leading whitespace in origination reported')
        # - eadid regex
        self.assert_("eadid '%s' does not match site URL regular expression" % ead.eadid.value
                    in errors, 'eadid regex error reported')

        #ARK in url and identifier not set or invalid
        self.assert_("eadid url is either not set or not an ARK. " +
            "To correct, run the prep process again."
                    in errors, 'eadid ark not in url')
        self.assert_("eadid identifier is either not set or not an ARK" +
            "To correct, run the prep process again."
                    in errors, 'eadid ark not in identifier')

        #valid ARKs in url and identifier but do not match
        ark1 = "http://testpid.library.emory.edu/ark:/25593/1234"
        ark1_short = "ark:/25593/1234"
        ark2_short = "ark:/25593/567"
        ead.eadid.url = ark1
        ead.eadid.identifier = ark2_short
        errors = utils.check_eadxml(ead)

        self.assert_("eadid url is either not set or not an ARK. " +
            "To correct, run the prep process again."
                    not in errors, 'valid eadid ark set in url')
        self.assert_("eadid identifier is either not set or not an ARK" +
            "To correct, run the prep process again."
                    not in errors, 'valid eadid ark set in identifier')

        self.assert_("eadid url and identifier do not match: url '%s' should end with identifier '%s'" % (ark1, ark2_short)
                    in errors, 'eadid url and  identifier do not march')

        # Change url and identifier to match
        ead.eadid.url = ark1
        ead.eadid.identifier = ark1_short
        errors = utils.check_eadxml(ead)

        self.assert_("eadid url and identifier do not match: url '%s' should end with identifier '%s'" % (ark1, ark1_short)
                    not in errors, 'eadid url and  identifier march')

        # - list title first letter regex
        # simulate non-whitespace, non-alpha first letter in list title
        ead.list_title.node.text = "1234"  # list title is not normally settable; overriding for test
        errors = utils.check_eadxml(ead)
        self.assert_("First letter ('1') of list title field origination/persname does not match browse letter URL regex '%s'" \
                     % TITLE_LETTERS in errors, 'title first letter regex error reported')

        # empty/unset list title field
        ead.list_title.node.text = None
        errors = utils.check_eadxml(ead)
        self.assert_("List title seems to be empty" in errors)

        # - whitespace in control access terms
        self.assert_("Found leading whitespace in controlaccess term ' Gone with the wind (Motion picture)' (title)"
                    in errors, 'controlaccess title leading whitespace reported')
        self.assert_("Found leading whitespace in controlaccess term '  \t   Selznick, David O., 1902-1965.' (persname)"
                    in errors, 'controlaccess name leading whitespace reported')
        self.assert_("Found leading whitespace in controlaccess term '  \t   Mines and mineral resources--Georgia.' (subject)"
                    in errors, 'controlaccess subject leading whitespace reported')
        self.assert_("Found leading whitespace in controlaccess term ' Motion pictures.' (genreform)"
                    in errors, 'controlaccess genre leading whitespace reported')

        # - did with > 2 containers
        self.assert_('Site expects maximum of 2 containers per did; found 1 did(s) with more than 2'
                    in errors, 'did with more than 2 containers reported')

        # - did with only 1 container
        self.assert_('Site expects 2 containers per did; found 1 did(s) with only 1'
                    in errors, 'did with only 1 container reported')

        # make sure we handle quirky document with a <title> at the beginning of the <unittitle>
        eadfile = os.path.join(settings.BASE_DIR, 'fa',
            'tests', 'fixtures', 'pittsfreeman1036.xml')
        ead_nested_title = load_xmlobject_from_file(eadfile, FindingAid)
        errors = utils.check_eadxml(ead_nested_title)
        self.assert_(all('list title' not in err for err in errors),
                     'nested <title> in <unittitle> should not generate a list title whitespace error')

    def test_prep_ead(self):
        # valid fixtures is an ead with series/subseries, and index
        # - clear out fixture ark url to trigger generating a new one (simulated)
        del(self.valid_ead.eadid.url)
        del(self.valid_ead.eadid.identifier)
        ead = utils.prep_ead(self.valid_ead, self.valid_eadfile)
        self.assert_(isinstance(ead, FindingAid), "prep_ead should return an instance of FindingAid")
        self.assertEqual(u'hartsfield558', ead.eadid.value)
        self.assertEqual(u'hartsfield558_series1', ead.dsc.c[0].id)
        self.assertEqual(u'hartsfield558_subseries6.1', ead.dsc.c[5].c[0].id)
        self.assertEqual(u'hartsfield558_index1', ead.archdesc.index[0].id)
        # ark should be generated and stored in eadid url
        self.assertEqual(MockDjangoPidmanClient.test_ark, ead.eadid.url)
        # short-form ark should be stored in identifier attribute
        self.assert_(MockDjangoPidmanClient.test_ark.endswith(ead.eadid.identifier))

        # ead with no series
        eadfile = os.path.join(settings.BASE_DIR, 'fa', 'tests',
            'fixtures', 'pittsfreeman1036.xml')
        ead = load_xmlobject_from_file(eadfile, FindingAid)
        ead = utils.prep_ead(ead, eadfile)
        self.assert_(isinstance(ead, FindingAid), "prep_ead should return an instance of FindingAid")
        self.assertEqual(u'pittsfreeman1036', ead.eadid.value)

        # series with no unitid
        eadfile = os.path.join(settings.BASE_DIR, 'fa', 'tests',
            'fixtures', 'raoul548.xml')
        ead = load_xmlobject_from_file(eadfile, FindingAid)
        ead = utils.prep_ead(ead, eadfile)
        self.assertEqual(u'raoul548_series3', ead.dsc.c[2].id)

        # whitespace cleanup
        ead = utils.prep_ead(self.invalid_ead, self.invalid_eadfile)
        # - no leading whitespace in list title
        # ead.archdesc.origination is getting normalized, so can't be used for testing
        origination = ead.node.xpath('//e:origination/e:persname', namespaces={'e': EAD_NAMESPACE})
        self.assertEqual(u'Hartsfield, William Berry.', origination[0].text)
        # test the node text directly (does not include unitdate)
        self.assertEqual(u'William Berry Hartsfield papers, ', ead.unittitle.node.text)
        self.assertEqual(u'Gone with the wind (Motion picture)',
                        ead.archdesc.controlaccess.controlaccess[0].title[0].value)
        self.assertEqual(u'Allen, Ivan.',
                        ead.archdesc.controlaccess.controlaccess[1].person_name[0].value)
        self.assertEqual(u'Mines and mineral resources--Georgia.',
                        ead.archdesc.controlaccess.controlaccess[3].subject[1].value)
        # unicode characters
        self.assertEqual(u'Motion pictures--Georgia. \u2026',
                        ead.archdesc.controlaccess.controlaccess[3].subject[2].value)
        self.assertEqual(u'Motion pictures.',
                        ead.archdesc.controlaccess.controlaccess[-1].genre_form[0].value)
        # remaining errors after clean-up:
        # 1 - duplicate origination
        # 2 - > 2 containers in a did (summary error and list of problem dids)
        # 2 - 1 container in a did (summary error and list of problem dids)
        # = 5
        self.assertEqual(5, len(utils.check_eadxml(ead)),
            "only 3 errors (duplicate origination, 3 containers in a did, 1 container in a did) should be left in invalid test fixture after cleaning")

        # special case - unittitle begins with a <title>
        eadfile = os.path.join(settings.BASE_DIR, 'fa', 'tests',
            'fixtures', 'pittsfreeman1036.xml')
        ead = load_xmlobject_from_file(eadfile, FindingAid)
        ead = utils.prep_ead(ead, eadfile)
        self.assertFalse(unicode(ead.list_title).startswith('None'),
            'cleaned unittitle with leading <title> should not start with "None"')

    def test_generate_ark(self):
        # successful case
        utils.generate_ark(self.valid_ead)
        self.assertEqual(MockDjangoPidmanClient.url,
                        settings.SITE_BASE_URL.rstrip('/') + '/documents/hartsfield558/',
                        'pid target URI is site url for ead document')
        self.assertEqual(MockDjangoPidmanClient.name, unicode(self.valid_ead.unittitle),
                        'pid name is ead document unittitle')
        self.assertEqual(settings.PIDMAN_DOMAIN, MockDjangoPidmanClient.domain,
                        'create pid used configured site pid domain')

    def test_generate_ark_badconfig(self):
        # missing config settings required for initializing pidman client
        del(settings.PIDMAN_HOST)
        # capture the exception to do minimal inspecting
        try:
            utils.generate_ark(self.valid_ead)
        except Exception as e:
            ex = e

        self.assert_('Error initializing' in str(ex))

    def test_generate_ark_nodomain(self):
        # missing config settings for pid domain
        del(settings.PIDMAN_DOMAIN)
        # capture the exception to inspect it
        try:
            utils.generate_ark(self.valid_ead)
        except Exception as e:
            ex = e

        self.assert_('PID manager domain is not configured' in str(ex))

    def test_generate_ark_serviceerror(self):
        MockDjangoPidmanClient.raise_error = (401, 'unauthorized')
        # handle errors that could come back from the server
        try:
            utils.generate_ark(self.valid_ead)
        except Exception as e:
            ex = e
        self.assert_(isinstance(ex, Exception),
            "an exception should be raised when PID client gets a 401 response")
        self.assert_('Error generating ARK' in str(ex),
            'exception text indicates the error was while attempting to generate an ARK')
        self.assert_('unauthorized' in str(ex),
            'exception text includes error detail from pidmanclient exception')

    def test_generate_ark_existing_pid(self):
        # simulate search finding one ark before new ark is generated
        found_ark = 'http://pid.emory.edu/ark:/78912/16x3n'
        # create mock search result with one match
        MockDjangoPidmanClient.search_result = {
            'results_count': 1,
            'results': [
                {
                    'pid': '16x3n',
                    'targets': [{'access_uri': found_ark}, ]
                },
            ]
        }

        # capture logging output in a stream
        buffer = cStringIO.StringIO()
        logger = logging.getLogger()
        sh = logging.StreamHandler(buffer)
        sh.setLevel(logging.DEBUG)
        logger.addHandler(sh)

        ark = utils.generate_ark(self.valid_ead)

        logger.removeHandler(sh)
        log_output = buffer.getvalue()

        self.assertEqual(found_ark, ark,
            'generate ark returns access uri from search results')
        search_args = MockDjangoPidmanClient.search_args
        self.assertEqual(settings.PIDMAN_DOMAIN, search_args['domain_uri'],
            'pid search uses configured PID domain')
        self.assertEqual('ark', search_args['type'],
            'pid search is restricted to type=ark')
        self.assert_(search_args['target'].endswith('/documents/hartsfield558/'))
        self.assert_('Using existing ARK' in log_output,
            'log reports an existing ARK was used')

    def test_generate_ark_existing_pids(self):
        # simulate search finding multiple pids
        found_ark = 'http://pid.emory.edu/ark:/78912/16x3n'
        # create mock search result with two matches
        MockDjangoPidmanClient.search_result = {
            'results_count': 2,
            'results': [
                {
                    'pid': '16x3n',
                    'targets': [{'access_uri': found_ark}, ]
                },
            ]
        }
        # capture logging output in a stream
        buffer = cStringIO.StringIO()
        logger = logging.getLogger()
        sh = logging.StreamHandler(buffer)
        sh.setLevel(logging.DEBUG)
        logger.addHandler(sh)

        ark = utils.generate_ark(self.valid_ead)

        logger.removeHandler(sh)
        log_output = buffer.getvalue()

        self.assertEqual(found_ark, ark,
            'generate ark returns access uri from search results')
        self.assert_('Found 2 ARKs' in log_output,
            'log reports that multiple ARKs were found')


### unit tests for findingaids.fa_admin.tasks

def _celerytest_setUp(testcase):
    # ensure required settings are available for testing
    if hasattr(settings, 'PROXY_HOST'):
        testcase.proxy_host = settings.PROXY_HOST
        setattr(settings, 'PROXY_HOST', 'myproxy:10101')
    if hasattr(settings, 'SITE_BASE_URL'):
        testcase.site_base_url = settings.SITE_BASE_URL
        setattr(settings, 'SITE_BASE_URL', 'http://findingaids.test.edu')

    # OK, this is a little weird: swap out the real httplib in tasks with
    # the mock httplib object defined above
    # testcase.real_httplib = tasks.httplib
    # testcase.mock_httplib = MockHttplib()
    # tasks.httplib = testcase.mock_httplib


def _celerytest_tearDown(testcase):
        if testcase.proxy_host:
            settings.PROXY_HOST = testcase.proxy_host
        if testcase.site_base_url:
            settings.SITE_BASE_URL = testcase.site_base_url


@patch.object(settings, 'CELERY_ALWAYS_EAGER', new=True)
class ReloadCachedPdfTestCase(TestCase):

    def setUp(self):
        _celerytest_setUp(self)

    def tearDown(self):
        _celerytest_tearDown(self)

    @patch('findingaids.fa_admin.tasks.urllib2')
    def test_success(self, mockurllib2):
        # set mock response to return 200
        mockurllib2.urlopen.return_value.code = 200
        #request = urllib2.Request(url, None, refresh_cache)
        #response = urllib2.urlopen(request)
        #logger.debug('Response headers: \n%s' % response.info())
        result = tasks.reload_cached_pdf.delay('eadid')
        result.task_id = 'random_id'
        self.assertEquals(True, result.get(),
            "for http status 200, task result returns True")
        self.assertTrue(result.successful(),
            "for http status 200, task result successful() returns True")

        # inspect mock urllib2 objects to confirm correct urls were used
        #proxy_args, proxy_kwargs = mockurllib2.ProxyHandler.call_args
        mockurllib2.ProxyHandler.assert_called_with({'http': settings.PROXY_HOST})
#        print 'debug proxy args are ', proxy_args
        # self.assertEqual(settings.PROXY_HOST, proxy_args['http'],
        #     "http connection should use PROXY_HOST from settings; expected %s, got %s" \
        #     % (settings.PROXY_HOST, proxy_args['http']))

        rqst_args, rqst_kwargs = mockurllib2.Request.call_args
        # request args : url, data, headers
        rqst_url = rqst_args[0]
        rqst_headers = rqst_args[2]
        self.assert_(rqst_url.startswith(settings.SITE_BASE_URL),
                     "http request url should begin with SITE_BASE_URL from settings; expected starting with %s, got %s" \
                     % (settings.SITE_BASE_URL, rqst_url))
        pdf_url = reverse('fa:printable', kwargs={'id': 'eadid'})
        self.assert_(rqst_url.endswith(pdf_url),
            "http request url should end with PDF url; expected ending with %s, got %s" \
            % (pdf_url, rqst_url))

        self.assertEqual(rqst_headers['Cache-Control'], 'max-age=0')

    @patch('findingaids.fa_admin.tasks.urllib2')
    def test_404(self, mockurllib2):
        # set the response to mock returning a 404 error
        mockurllib2.urlopen.return_value.code = 404
        result = tasks.reload_cached_pdf.delay('eadid')
        self.assertRaises(Exception, result.get,
            "for http status 404, task result raises an Exception")
        self.assertFalse(result.successful(),
            "for http status 404, task result successful() is not True")

    def test_missing_settings(self):
        delattr(settings, 'PROXY_HOST')
        delattr(settings, 'SITE_BASE_URL')

        result = tasks.reload_cached_pdf.delay('eadid')
        self.assertRaises(Exception, result.get,
            "when required settings are missing, task raises an Exception")


### unit tests for django-admin manage commands

class TestCommand(BaseCommand):
    output = ''
    # test command class to simplify calling a command as if running from the commandline
    # base command will set up default args before calling handle method

    def run_command(self, *args):
        '''Run the command as if calling from command line by giving a list
        of command-line arguments, e.g.::

            command.run_command('-n', '-v', '2')

        :param args: list of command-line arguments
        '''
        # capture stdout & stderr for testing output results
        buffer = cStringIO.StringIO()
        sys.stdout = buffer
        sys.stderr = buffer
        try:
            # run from argv expects command, subcommand, then any arguments
            run_args = ['manage.py', 'command-name']
            run_args.extend(args)
            result = self.run_from_argv(run_args)
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__

        self.output = buffer.getvalue()

        return result


class PrepEadTestCommand(prep_ead_cmd.Command, TestCommand):
    pass


class PrepEadCommandTest(TestCase):
    def setUp(self):
        self.command = PrepEadTestCommand()
        # store settings that may be changed/removed by tests
        self._ead_src = settings.FINDINGAID_EAD_SOURCE
        self._existdb_root = settings.EXISTDB_ROOT_COLLECTION
        self._pidman_pwd = settings.PIDMAN_PASSWORD

        self.tmpdir = tempfile.mkdtemp(prefix='findingaids-prep_ead-test')
        settings.FINDINGAID_EAD_SOURCE = self.tmpdir

        settings.PIDMAN_PASSWORD = 'this-better-not-be-a-real-password'

        # temporarily replace pid client with mock for testing
        self._django_pid_client = prep_ead_cmd.utils.DjangoPidmanRestClient
        prep_ead_cmd.utils.DjangoPidmanRestClient = MockDjangoPidmanClient

        self.files = {}
        self.file_sizes = {}    # store file sizes to check modification
        fixture_dir = os.path.join(settings.BASE_DIR, 'fa_admin', 'fixtures')
        for file in ['hartsfield558.xml', 'hartsfield558_invalid.xml', 'badlyformed.xml']:
            # store full path to tmp copy of file
            self.files[file] = os.path.join(self.tmpdir, file)
            copyfile(os.path.join(fixture_dir, file), self.files[file])
            self.file_sizes[file] = os.path.getsize(self.files[file])

    def tearDown(self):
        # remove any files created in temporary test staging dir
        rmtree(self.tmpdir)
        # restore real settings
        settings.FINDINGAID_EAD_SOURCE = self._ead_src
        settings.EXISTDB_ROOT_COLLECTION = self._existdb_root
        settings.PIDMAN_PASSWORD = self._pidman_pwd

        MockDjangoPidmanClient.search_result = MockDjangoPidmanClient.search_result_nomatches
        prep_ead_cmd.utils.DjangoPidmanRestClient = self._django_pid_client

    def test_missing_ead_source_setting(self):
        del(settings.FINDINGAID_EAD_SOURCE)
        self.assertRaises(CommandError, self.command.handle, verbosity=0)

    def test_missing_existdb_setting(self):
        del(settings.EXISTDB_ROOT_COLLECTION)
        self.assertRaises(CommandError, self.command.handle, verbosity=0)

    def test_prep_all(self):
        # force ark generation error
        MockDjangoPidmanClient.raise_error = (401, 'unauthorized')

        # with no filenames - should process all files
        self.command.run_command('-v', '2')
        output = self.command.output

        # badly-formed xml - should be reported
        self.assert_(re.search(r'^Error.*badlyformed.xml.*not well-formed.*$', output, re.MULTILINE),
            'prep_ead reports error for non well-formed xml')
        # invalid - should result in error on attempted ark generation
        self.assert_(re.search(r'Error: failed to prep .*hartsfield558_invalid.xml', output),
            'prep_ead reports prep/ark generation error')
        self.assert_(re.search(r'Updated .*hartsfield558.xml', output),
            'in verbose mode, prep_ead reports updated document')

        # files with errors should not be modified
        self.assertEqual(self.file_sizes['hartsfield558_invalid.xml'],
                        os.path.getsize(self.files['hartsfield558_invalid.xml']),
                    'file with errors not modified by prep_ead script when updating all documents')
        self.assertEqual(self.file_sizes['badlyformed.xml'],
                        os.path.getsize(self.files['badlyformed.xml']),
                    'file with errors not modified by prep_ead script when updating all documents')

    def test_prep_single(self):
        # copy valid file so there are two files that could be changed
        hfield_copy = os.path.join(self.tmpdir, 'hartsfield558-2.xml')
        copyfile(os.path.join(settings.BASE_DIR, 'fa_admin', 'fixtures', 'hartsfield558.xml'),
                 hfield_copy)
        self.file_sizes['hartsfield558-2.xml'] = os.path.getsize(hfield_copy)

        # process a single file
        self.command.run_command('hartsfield558.xml')
        output = self.command.output

        self.assert_('1 document updated' in output)
        self.assert_('0 documents unchanged' in output)
        self.assert_('0 documents with errors' in output)

        # using file-size as a convenient way to check which files were modified
        self.assertNotEqual(self.file_sizes['hartsfield558.xml'],
                            os.path.getsize(self.files['hartsfield558.xml']),
                            'specified file was modified by prep_ead script')
        self.assertEqual(self.file_sizes['hartsfield558-2.xml'],
                        os.path.getsize(hfield_copy),
                    'in single-file mode, non-specified file not modified by prep_ead script')

    def test_prep_ark_messages(self):
        MockDjangoPidmanClient.search_result = {
            'results_count': 2,
            'results': [
                {
                    'pid': '16x3n',
                    'targets': [{'access_uri': 'http://pid/ark:/123/34c'}, ]
                },
            ]
        }

        # run on a single file where ark generation will be attempted
        self.command.run_command('hartsfield558_invalid.xml')
        output = self.command.output

        self.assert_('WARNING: Found 2 ARKs' in output)
        self.assert_('INFO: Using existing ARK' in output)


class UnitidIdentifierTestCommand(unitid_identifier.Command, TestCommand):
    pass


class UnitidIdentifierCommandTest(TestCase):
    def setUp(self):
        self.command = UnitidIdentifierTestCommand()
        # store settings that may be changed/removed by tests
        self._ead_src = settings.FINDINGAID_EAD_SOURCE

        self.tmpdir = tempfile.mkdtemp(prefix='findingaids-unitid_identifier-test')
        settings.FINDINGAID_EAD_SOURCE = self.tmpdir

        self.files = {}
        self.file_sizes = {}    # store file sizes to check modification
        fixture_dir = os.path.join(settings.BASE_DIR, 'fa_admin', 'fixtures')
        for file in ['hartsfield558.xml', 'hartsfield558_invalid.xml', 'badlyformed.xml']:
            # store full path to tmp copy of file
            self.files[file] = os.path.join(self.tmpdir, file)
            copyfile(os.path.join(fixture_dir, file), self.files[file])
            self.file_sizes[file] = os.path.getsize(self.files[file])

    def tearDown(self):
        # remove any files created in temporary test staging dir
        rmtree(self.tmpdir)
        # restore real settings
        settings.FINDINGAID_EAD_SOURCE = self._ead_src

    def test_run(self):
        # process all files
        self.command.run_command('-v', '2')
        output = self.command.output

        # check that correct unitid identifier was set
        ead = load_xmlobject_from_file(self.files['hartsfield558.xml'], FindingAid)
        self.assertEqual(558, ead.archdesc.unitid.identifier)
        self.assert_('2 documents updated' in output)
        self.assert_('1 document with errors' in output)

        # badly-formed xml - should be reported
        self.assert_(re.search(r'^Error.*badlyformed.xml.*not well-formed.*$', output, re.MULTILINE),
            'unitid_identifier reports error for non well-formed xml')

        # files with errors should not be modified
        self.assertEqual(self.file_sizes['badlyformed.xml'],
                        os.path.getsize(self.files['badlyformed.xml']),
                    'file with errors not modified by unitid_identifier script')