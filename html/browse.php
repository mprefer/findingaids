<?php
include("common_functions.php");
include_once("config.php");
include_once("lib/xmlDbConnection.class.php");

$args = array('host' => $tamino_server,
	      'db' => $tamino_db,
	      'coll' => $tamino_coll,
	      'debug' => false);

$tamino = new xmlDbConnection($args);

switch ($browseBy)
{
	case 'unittitle':
	default:
		$search_path = "/archdesc/did/origination/persname";
		// query for all volumes 
}

$browse_qry = "
	for \$b in 
	distinct-values
	(
		for \$a in 
		(
			input()/ead/archdesc/did/origination/persname,
			input()/ead/archdesc/did/origination/corpname,
			input()/ead/archdesc/did/origination/famname,
			input()/ead/archdesc/did/unittitle
		)
		let \$l := substring(\$a,1,1)
		return \$l
	)
	return <letter>{\$b}</letter>
";



$letter = ($_REQUEST['l']) ? $_REQUEST['l'] : 'A';
if ($letter != 'all')
{
	$letter_search =  " where substring(\$a/archdesc/did/origination/persname,1,1) = '$letter' ";
	$letter_search .= " or substring(\$a/archdesc/did/origination/corpname,1,1) = '$letter' ";
	$letter_search .= " or substring(\$a/archdesc/did/origination/famname,1,1) = '$letter' ";
} else {
	$letter_search = "";
}

$data_qry = "
	for \$a in input()/ead
	$letter_search
	return <record>
			{\$a/@id}
			<name>
				{\$a/archdesc/did/origination/persname}
				{\$a/archdesc/did/origination/corpname}
				{\$a/archdesc/did/origination/famname}
			</name>
			{\$a/archdesc/did/unittitle}
			{\$a/archdesc/did/physdesc}
			{\$a/archdesc/did/abstract}
			<sort-title>
				{string(\$a/archdesc/did/origination/persname)}
				{string(\$a/archdesc/did/origination/corpname)}
				{string(\$a/archdesc/did/origination/famname)}			
				{string(\$a/archdesc/did/unittitle)}			
			</sort-title>
		   </record>
   	sort by (sort-title)
";

/*
{ for \$i in (\" \", \"'\", \"A \", \"An \", \"The \", \"\", \"The Register of the \", \"A Register of \", \"The Register of \", \"Register of \", \"Register \") where starts-with(\$a/archdesc/did/unittitle, \$i)
			 	return substring-after(\$a/archdesc/did/unittitle, \$i) }
*/

$alpha_list = file_get_contents("browse-ndx.xml");
$query = "<results>$alpha_list<records>{".$data_qry."}</records></results>";
//$query = "<results><alpha_list>{".$browse_qry."}</alpha_list> <records>{".$data_qry."}</records></results>";

$mode = 'browse';

$xsl_file 	= "stylesheets/results.xsl";
$xsl_params = array('mode' => $mode, 'label_text' => "Browse Collections Alphabetically:", 'baseLink' => "browse-coll");

$rval = $tamino->xquery(trim($query));
$tamino->xslTransform($xsl_file, $xsl_params);

echo "<link rel=\"stylesheet\" type=\"text/css\" href=\"http://biliku.library.emory.edu/jbwhite/projects/marblfa-php/html/css/marblfa.css\">\n";
print '<div class="content">';
$tamino->printResult();
print '</div>';
?>
