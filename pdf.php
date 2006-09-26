<?
include_once("config.php");
include_once("lib/xmlDbConnection.class.php");

$id = $_GET["id"];

$query = "/ead[@id = '$id']";

$connectionArray{"debug"} = false;

$xmldb = new xmlDbConnection($connectionArray);

$xsl = "stylesheets/marblpdf.xsl";

$xmldb->xquery($query);
//$xmldb->xslTransform($xsl);
$params = array("mode" => "full");
$xmldb->xslBind("stylesheets/marblfa.xsl", $params);
$xmldb->xslBind("stylesheets/htmlpdf.xsl");
$xmldb->transform();

$filename = $xmldb->findNode("eadheader/eadid");
$filename = basename($filename, ".xml");
$outfile = $tmpdir . $filename . '.fo';
mkdir($tmpdir);
$xmldb->save($outfile);
//print "DEBUG: saving xml (xsl-fo) to $outfile.<br>";

// call fop & generate pdf ...
$pdf  = file_get_contents($fop . $outfile);

header("Content-type: application/pdf");
header("Content-Disposition: filename=$filename.pdf");

print $pdf;

// remove temporary file
unlink($outfile);

?>