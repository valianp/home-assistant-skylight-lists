<#
Creates a Skylight Lists config entry through Home Assistant's supported
configuration-flow REST API. It neither automates a browser nor edits .storage.

Required environment variables:
  HA_URL, HA_TOKEN, SKYLIGHT_USERNAME, SKYLIGHT_PASSWORD, SKYLIGHT_FRAME_ID
#>

$ErrorActionPreference = "Stop"
$required = "HA_URL", "HA_TOKEN", "SKYLIGHT_USERNAME", "SKYLIGHT_PASSWORD", "SKYLIGHT_FRAME_ID"
$missing = $required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) }
if ($missing) { throw "Missing environment variables: $($missing -join ', ')" }

$baseUrl = $env:HA_URL.TrimEnd("/")
$headers = @{ Authorization = "Bearer $($env:HA_TOKEN)" }

try {
    # Start the same user-source config flow the Integration UI starts.
    $flow = Invoke-RestMethod -Method Post `
        -Uri "$baseUrl/api/config/config_entries/flow" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body (@{ handler = "skylight_lists" } | ConvertTo-Json -Compress)

    if (-not $flow.flow_id) { throw "Home Assistant did not return a config flow ID." }

    $result = Invoke-RestMethod -Method Post `
        -Uri "$baseUrl/api/config/config_entries/flow/$($flow.flow_id)" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body (@{
            username = $env:SKYLIGHT_USERNAME
            password = $env:SKYLIGHT_PASSWORD
            frame_id = $env:SKYLIGHT_FRAME_ID
        } | ConvertTo-Json -Compress)

    if ($result.type -ne "create_entry") {
        throw "Config flow did not create an entry: $($result | ConvertTo-Json -Compress -Depth 6)"
    }
    Write-Output "Skylight Lists was configured successfully."
} catch {
    $response = $_.Exception.Response
    if ($response) {
        $reader = [IO.StreamReader]::new($response.GetResponseStream())
        $details = $reader.ReadToEnd()
        throw "Home Assistant config flow failed: $details"
    }
    throw
}
