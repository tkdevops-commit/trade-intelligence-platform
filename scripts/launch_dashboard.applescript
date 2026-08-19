-- Trade Intelligence Platform macOS launcher.
-- Starts the local server quietly, then opens the browser dashboard.
on run
    set projectPath to "/Users/tg/trade-intelligence-platform"
    set launchScript to projectPath & "/scripts/launch_dashboard.sh"
    set commandText to "nohup " & quoted form of launchScript & " >/tmp/trade-intelligence-launcher.log 2>&1 &"

    try
        do shell script commandText
    on error errorMessage
        display dialog "The Trade Intelligence dashboard could not start. See /tmp/trade-intelligence-launcher.log for details.\n\n" & errorMessage buttons {"OK"} default button "OK" with icon stop
    end try
end run
