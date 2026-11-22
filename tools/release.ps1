param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = "",
    [switch]$Latest
)

$ErrorActionPreference = "Stop"
$root = "C:\Users\sanju\Desktop\umbral"
$dist = Join-Path $root "dist"
$exe = Join-Path $dist "Umbral.exe"
$shaFile = Join-Path $dist "Umbral.exe.sha256"
$gh = Join-Path $env:LOCALAPPDATA "Programs\gh\bin\gh.exe"
$repo = "sanjurjogon-crypto/umbral"

if ($Version -notmatch '^v?\d+(\.\d+){1,3}$') {
    throw "Version invalida: $Version. Usa por ejemplo v8.15.1"
}
$tag = $Version.TrimStart("v")
$tag = "v$tag"

if (-not (Test-Path -LiteralPath $exe)) {
    throw "No existe $exe. Compila antes con PyInstaller."
}
if (-not (Test-Path -LiteralPath $gh)) {
    throw "No existe gh en $gh."
}

$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLower()
"$hash *Umbral.exe" | Set-Content -LiteralPath $shaFile -Encoding ASCII

$notesFile = Join-Path $env:TEMP "umbral-release-$tag.md"
if ($Notes) {
    $cleanNotes = $Notes.Replace([string][char]0xFEFF, "")
    Set-Content -LiteralPath $notesFile -Value $cleanNotes -Encoding UTF8
} else {
    Set-Content -LiteralPath $notesFile -Value "Version $tag." -Encoding UTF8
}

$existing = $null
$previous = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $existing = & $gh release view $tag --repo $repo --json tagName --jq ".tagName" 2>$null
} catch {
    $existing = $null
}
$ErrorActionPreference = $previous
if ($existing) {
    "El release $tag ya existe; subo o reemplazo los archivos."
    & $gh release upload $tag $exe $shaFile --repo $repo --clobber
    & $gh release edit $tag --repo $repo --notes-file $notesFile
} else {
    $cmdArgs = @(
        "release", "create", $tag, $exe, $shaFile,
        "--repo", $repo,
        "--title", "Umbral $($tag.TrimStart('v'))",
        "--notes-file", $notesFile
    )
    if ($Latest) { $cmdArgs += "--latest" }
    & $gh @cmdArgs
}

& $gh release view $tag --repo $repo --json tagName,name,isDraft,isPrerelease,assets,url | Out-String
