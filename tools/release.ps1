param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = "",
    [switch]$Latest,
    [switch]$SkipBuild,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist"
$exe = Join-Path $dist "Umbral.exe"
$shaFile = Join-Path $dist "Umbral.exe.sha256"
$gh = Join-Path $env:LOCALAPPDATA "Programs\gh\bin\gh.exe"
if (-not (Test-Path -LiteralPath $gh)) {
    $command = Get-Command gh -ErrorAction SilentlyContinue
    if ($null -ne $command) { $gh = $command.Source }
}
$repo = "sanjurjogon-crypto/umbral"

if ($Version -notmatch '^v?\d+(\.\d+){1,3}$') {
    throw "Version invalida: $Version. Usa por ejemplo v8.15.1"
}
$tag = $Version.TrimStart("v")
$tag = "v$tag"

if (-not $SkipBuild) {
    Push-Location $root
    try {
        python -m PyInstaller --noconfirm Umbral.spec
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller fallo con codigo $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $exe)) {
    throw "No existe $exe. Compila antes con PyInstaller."
}
if (-not (Test-Path -LiteralPath $gh)) {
    throw "No existe gh en $gh."
}

# Comprueba que la version del codigo coincide con la que se publica.
$initPath = Join-Path $root "umbral\__init__.py"
$initText = Get-Content -LiteralPath $initPath -Raw -Encoding UTF8
$declared = [regex]::Match($initText, '__version__\s*=\s*"([^"]+)"').Groups[1].Value
if ($declared -ne $tag.TrimStart("v")) {
    throw "La version del codigo ($declared) no coincide con la del release ($($tag.TrimStart('v'))). Actualiza umbral\__init__.py antes de publicar."
}

# Sube el codigo fuente de esta version a GitHub.
$env:GIT_TERMINAL_PROMPT = "0"
git -C $root add -u
$sourceItems = @(
    "main.py",
    "umbral",
    "tools",
    "tests",
    ".github",
    "pytest.ini",
    "requirements.txt",
    "requirements-dev.txt",
    "README.md",
    "Umbral.spec",
    ".gitignore"
)
foreach ($item in $sourceItems) {
    $target = Join-Path $root $item
    if (Test-Path -LiteralPath $target) {
        git -C $root add -- $item
    }
}
git -C $root diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $staged = @(git -C $root diff --cached --name-only)
    Write-Host "Cambios que entraran en el commit de $tag :"
    $staged | ForEach-Object { Write-Host "  $_" }
    if (-not $Yes) {
        $answer = Read-Host "Continuar con la publicacion? (s/N)"
        if ($answer -notmatch '^[sSyY]') {
            throw "Publicacion cancelada. Revisa el arbol o vuelve a lanzar con -Yes."
        }
    }
    git -C $root commit -m "Umbral $tag"
}
$headCommit = (git -C $root rev-parse HEAD).Trim()
$existingTag = git -C $root tag --list $tag
$forceTag = $false
if (-not $existingTag) {
    git -C $root tag $tag
} else {
    $tagCommit = (git -C $root rev-list -n 1 $tag).Trim()
    if ($tagCommit -ne $headCommit) {
        git -C $root tag -f $tag
        $forceTag = $true
    }
}
git -C $root push origin main
if ($forceTag) {
    git -C $root push --force origin $tag
} else {
    git -C $root push origin $tag
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
        "--target", "main",
        "--title", "Umbral $($tag.TrimStart('v'))",
        "--notes-file", $notesFile
    )
    if ($Latest) { $cmdArgs += "--latest" }
    & $gh @cmdArgs
}

& $gh release view $tag --repo $repo --json tagName,name,isDraft,isPrerelease,assets,url | Out-String

$pinnedDir = Join-Path $env:APPDATA "Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
$syncedTargets = @()
if (Test-Path -LiteralPath $pinnedDir) {
    $shell = New-Object -ComObject WScript.Shell
    Get-ChildItem -LiteralPath $pinnedDir -Filter "*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $shortcut = $shell.CreateShortcut($_.FullName)
            $targetPath = [string]$shortcut.TargetPath
            if ($targetPath -and ([System.IO.Path]::GetFileName($targetPath) -ilike "Umbral*.exe")) {
                $targetDir = Split-Path -Parent $targetPath
                if (Test-Path -LiteralPath $targetDir) {
                    $runningMatch = Get-Process -ErrorAction SilentlyContinue | Where-Object {
                        try { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -ieq [System.IO.Path]::GetFullPath($targetPath)) } catch { $false }
                    }
                    if ($null -eq $runningMatch) {
                        Copy-Item -LiteralPath $exe -Destination $targetPath -Force
                        $syncedTargets += $targetPath
                        Write-Host "Actualizado ejecutable anclado en barra de tareas: $targetPath"
                    } else {
                        Write-Host "No se pudo actualizar $targetPath porque esta en ejecucion."
                    }
                }
            }
        } catch {
        }
    }
}
if ($syncedTargets.Count -eq 0) {
    $downloadsFallback = Join-Path $env:USERPROFILE "Downloads\Umbral.exe"
    if (Test-Path -LiteralPath (Split-Path -Parent $downloadsFallback)) {
        $runningFallback = Get-Process -ErrorAction SilentlyContinue | Where-Object {
            try { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -ieq [System.IO.Path]::GetFullPath($downloadsFallback)) } catch { $false }
        }
        if ($null -eq $runningFallback) {
            Copy-Item -LiteralPath $exe -Destination $downloadsFallback -Force
            Write-Host "Actualizado ejecutable en Descargas: $downloadsFallback"
        }
    }
}
