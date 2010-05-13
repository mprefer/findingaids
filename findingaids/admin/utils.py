import os
from Ft.Xml import ReaderException
from eulcore.xmlmap.core import load_xmlobject_from_file
from findingaids.fa.models import FindingAid

def check_ead(filename, dbpath):
    """
    Sanity check an EAD file before it is loaded to the configured database.

    Checks the following:
     - DTD valid (file must include doctype declaration)
     - eadid matches expected pattern (filename without .xml)
     - check that eadid is unique within the database (only present once, in the file that will be updated)
     - series and index ids are present
     

    :param filename: full path to the EAD file to be checked
    :param dbpath: full path within eXist where the document will be saved
    :rtype list: list of all errors found
    """
    errors = []
    try:
        ead = load_xmlobject_from_file(filename, FindingAid, validate=True)
    except ReaderException, e:
        errors.append(e)
        # if not dtd-valid, load without validation to do additional checking
        ead = load_xmlobject_from_file(filename, FindingAid, validate=False)
    
    # eadid is expected to match filename without .xml extension
    expected_eadid = os.path.basename(filename).replace('.xml', '')
    if ead.eadid != expected_eadid :
        errors.append("eadid '%s' does not match expected value of '%s'" % (ead.eadid, expected_eadid))
    else:   # if eadid is acceptable, check for uniqueness in configured database
        fa = FindingAid.objects.filter(eadid=ead.eadid).only("document_name", "collection_name")
        if fa.count() > 1:
            errors.append("Database already contains %s instances of eadid '%s'! (%s)"
                    % (fa.count(), ead.eadid, ", ".join([f.document_name for f in fa])))
        elif fa.count() == 1:
            # some inconsistency in when /db is included on exist collection names
            path = fa[0].collection_name.replace('/db', '') + "/" + fa[0].document_name
            if path != dbpath:
                errors.append("Database contains eadid '%s' in a different document (%s)"
                    % (ead.eadid, fa[0].document_name))            

    # check that series ids are set
    if ead.dsc.hasSeries():
        for series in ead.dsc.c:
            errors.extend(_check_series_ids(series))

    # check that any index ids are set
    for index in ead.archdesc.index:
        if not index.id:
            errors.append("%(node)s id attribute is not set for %(label)s"
                % { 'node' : index.dom_node.nodeName, 'label' : index.head })
    return errors   
    


def _check_series_ids(series):
    # recursive function to check that series and subseries ids are present
    errors = []
    if not series.id:
        errors.append("%(level)s %(node)s id attribute is not set for %(label)s"
                % { 'node' : series.dom_node.nodeName, 'level' : series.level, 'label' : series.display_label() })
    if series.hasSubseries():
        for c in series.c:
            errors.extend(_check_series_ids(c))
    return errors
    