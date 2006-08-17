<?php

// php functions & variables used by more than one ILN php page
include("config.php");


/* 12.10.2004 - Added robots meta line to header, partially as a test
   to see if it would help google to index the actual articles.
*/

function html_head ($mode, $contentlist = false) {
  global $base_url;	// use base url as set in site-wide config file
print "<html>
 <head>
 <title>$mode - Manuscript, Archives, and Rare Books Library</title>
<meta http-equiv=\"Content-Type\" content=\"text/html; charset=iso-8859-1\">
<meta name=\"robots\" content=\"index,follow\">
 </head>";
}



// convert a readable xquery into a clean url
function encode_url ($string) {
  // get rid of multiple white spaces
  $string = preg_replace("/\s+/", " ", $string);
  // convert spaces to hex equivalent
  $string = str_replace(" ", "%20", $string);
  return $string;
}

// param arg is optional - defaults to null
function transform ($xml_file, $xsl_file, $xsl_params = NULL) {
	$xsl = new DomDocument();
	$xsl->load($xsl_file);
	
	$xml = new DOMDocument();
	$xml->load($xml_file);
	
	/* create processor & import stylesheet */
	$proc = new XsltProcessor();
	$proc->importStylesheet($xsl);
	if ($xsl_params) {
		foreach ($xsl_params as $name => $val) {
			$proc->setParameter(null, $name, $val);
		}
	}
	/* transform the xml document and store the result */
	$xsl_result = $proc->transformToDoc($xml);
	
	return $xsl_result;
}

//Function that takes multiple terms separated by white spaces and puts them into an array
function processterms ($str) {
// clean up input so explode will work properly
    $str = preg_replace("/\s+/", " ", $str);  // multiple white spaces become one space
    $str = preg_replace("/\s$/", "", $str);	// ending white space is removed
    $str = preg_replace("/^\s/", "", $str);  //beginning space is removed
    $terms = explode(" ", $str);    // multiple search terms, divided by spaces
    return $terms;
}



// display bread crumbs
function displayBreadCrumbs($array_bc)
{
	$rv = '';
	if (is_array($array_bc))
	{
		//foreach ($array_bc as $bc)
		for($i=0;$i<count($array_bc);$i++)
		{
			$bc = $array_bc[$i];
			if ($bc['href'] != '')
			{
				$rv .= " <a href=\"" . $bc['href'] . "\">" . $bc['anchor'] . "</a> ";
			} else {
				$rv .= " ".$bc['anchor'];
			}
		}
	}
		
	$rv = rtrim($rv, ",");
	
	print "<div class=\"breadCrumbs\">$rv</div>";
}

?>