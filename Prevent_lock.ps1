Add-Type -AssemblyName System.Windows.Forms

Write-Host "Scroll Lock toggling started to prevent screen lock"

While ($true) {
      [System.Windows.Forms.SendKeys]::SendWait("{SCROLLLOCK}")
      Start-Sleep -Seconds 30

      [System.Windows.Forms.SendKeys]::SendWait("{SCROLLLOCK}")
      Start-Sleep -Seconds 30
}