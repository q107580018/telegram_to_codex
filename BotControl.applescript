property projectPath : "/Users/mac/Documents/test"

on isBotRunning()
	set checkCmd to "cd " & quoted form of projectPath & " && if [ -f bot.pid ]; then pid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$pid\" ] && ps -p \"$pid\" >/dev/null 2>&1; then echo running; exit 0; fi; fi; if pgrep -f " & quoted form of (projectPath & "/bot.py") & " >/dev/null 2>&1; then echo running; else echo stopped; fi"
	set stateText to do shell script checkCmd
	return stateText is "running"
end isBotRunning

on startBot()
	set cmd to "cd " & quoted form of projectPath & " && if [ -f bot.pid ]; then oldpid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$oldpid\" ] && ps -p \"$oldpid\" >/dev/null 2>&1; then echo already_running; exit 0; fi; fi; nohup " & quoted form of (projectPath & "/.venv/bin/python") & " " & quoted form of (projectPath & "/bot.py") & " >> bot.log 2>&1 & newpid=$!; echo $newpid > bot.pid; sleep 1; if ps -p \"$newpid\" >/dev/null 2>&1; then echo started; else echo failed; fi"
	return do shell script cmd
end startBot

on stopBot()
	set cmd to "cd " & quoted form of projectPath & " && ./stop.sh >/dev/null 2>&1 || true && echo stopped"
	return do shell script cmd
end stopBot

on showLog()
	set cmd to "cd " & quoted form of projectPath & " && if [ -f bot.log ]; then tail -n 40 bot.log; else echo '暂无日志'; fi"
	return do shell script cmd
end showLog

on showStatus()
	set statusText to "已停止"
	if isBotRunning() then set statusText to "Running"
	
	if statusText is "Running" then set statusText to "运行中"
	set msg to "Telegram Bot 控制器" & return & return & "项目路径: " & projectPath & return & "当前状态: " & statusText
	
	try
		set choice to button returned of (display dialog msg buttons {"退出并停止", "操作", "启动"} default button "启动")
	on error number -128
		stopBot()
		return false
	end try
	
	if choice is "启动" then
		set resultText to startBot()
		display dialog "启动结果: " & resultText buttons {"确定"} default button "确定"
		return true
	else if choice is "操作" then
		try
			set op to choose from list {"刷新", "停止", "查看日志"} with prompt "选择一个操作：" default items {"刷新"} OK button name "确定" cancel button name "取消"
		on error number -128
			stopBot()
			return false
		end try
		if op is false then
			return true
		end if
		set opName to item 1 of op
		if opName is "停止" then
			set resultText to stopBot()
			display dialog "停止结果: " & resultText buttons {"确定"} default button "确定"
		else if opName is "查看日志" then
			set logText to showLog()
			if length of logText > 1800 then set logText to text 1 thru 1800 of logText & return & "...(日志已截断)"
			display dialog logText buttons {"确定"} default button "确定"
		end if
		return true
	else if choice is "刷新" then
		return true
	else
		stopBot()
		return false
	end if
end showStatus

repeat
	set keepGoing to showStatus()
	if keepGoing is false then exit repeat
end repeat
