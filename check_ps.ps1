$path = "start.ps1"
$err = $null
$tokens = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path).Path, [ref]$tokens, [ref]$err)
if ($err) { 
    $err | ForEach-Object { "[{0}:{1}] {2}" -f $_.Extent.StartLineNumber, $_.Extent.StartColumnNumber, $_.Message }
}
else { 
    "No errors"
}
