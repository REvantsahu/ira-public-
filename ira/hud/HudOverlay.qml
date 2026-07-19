import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15
import QtWebEngine


Window {
    id: root
    visible: true
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    width: screen ? screen.width : Screen.width
    height: screen ? screen.height : Screen.height
    visibility: Window.FullScreen

    // ── PANEL VISIBILITY ──────────────────────────
    property bool rightPanelShown: false
    property bool dockExpanded: true
    property bool chatPopupShown: false
    property bool chatExpanded: false
    property bool searchWindowShown: false
    property int bottomMargin: 85
    property bool showNodes: true
    property bool isBooting: true
    property int bootPhase: 0
    property bool todoSectionVisible: false
    property bool autoDetectEnabled: true
    property bool gesturesEnabled: true
    property bool reasoningEnabled: true
    property string reasoningLevel: "high"
    property bool autoScreenshotEnabled: true
    property string userLocation: "Detecting..."
    property real userLat: 19.8762
    property real userLng: 75.3704

    // ── INSTANT HOTSPOT RE-REGISTRATION ON STATE CHANGES ──
    onRightPanelShownChanged: { registerHotspots(); hotspotTimer.restart() }
    onDockExpandedChanged: { registerHotspots(); hotspotTimer.restart() }
    onChatPopupShownChanged: { registerHotspots(); hotspotTimer.restart() }
    onChatExpandedChanged: { registerHotspots(); hotspotTimer.restart() }
    onSearchWindowShownChanged: { registerHotspots(); hotspotTimer.restart() }
    onToolWindowShownChanged: { registerHotspots(); hotspotTimer.restart() }
    onMemoryWindowShownChanged: { registerHotspots(); hotspotTimer.restart() }
    onLeftPanelShownChanged: { registerHotspots(); hotspotTimer.restart(); bridge.setGestureMonitorVisible(leftPanelShown); if (leftPanelShown) { activeModels = JSON.parse(bridge.getActiveModels()) } }
    onShowNodesChanged: { registerHotspots(); hotspotTimer.restart() }
    onAttachedImageChanged: { registerHotspots(); hotspotTimer.restart() }
    onAttachedLargeTextChanged: { registerHotspots(); hotspotTimer.restart() }
    onIsVoiceModeChanged: { registerHotspots(); hotspotTimer.restart() }

    // ── SCREENSHOT FLASH OVERLAY ──────────────────────────
    // Removed to prevent white screen getting stuck.

    // Called from Python via QMetaObject.invokeMethod
    function fadeOutOverlay() {}
    function fadeInOverlay() {}

    // ── CHAT ATTACHMENTS (multi) ──────────────────
    property int maxAttachments: 12
    property string attachedImage: ""       // legacy compat — first image path
    property string attachedLargeText: ""   // legacy compat — first text full
    property string attachedLargeTextPreview: "" // legacy compat — first text preview

    // ── CHAT LOGS ──────────────────────────────────
    property string toolLogs: ""
    property string cameraFrameBase64: ""
    property string gestureLogText: ""
    property var activeModels: ({})

    // ── SYSTEM DATA ──────────────────────────────
    property real cpuVal: 0
    property real ramVal: 0
    property real batVal: 0
    property string ramUsedStr: "?"
    property string ramTotalStr: "?"
    property bool isCharging: false

    // ── AVATAR STATE ────────────────────────────
    property string avatarState: "idle"
    property real avatarOpacity: 0.9
    property bool showAvatar: true
    property string currentExpression: "normal"
    property int mouseX: 0
    property int mouseY: 0

    // ── CHAT STATE ───────────────────────────────
    property string currentUserText: ""
    property string currentIraText: ""
    property bool userMsgExpanded: false
    property bool iraMsgExpanded: false
    property bool isProcessing: false
    property string processingStatusText: "Working on it..."
    property var processingPhrases: [
        "Analyzing screen context...",
        "Sabar karo, main dekh rahi hoon...",
        "Working on it, almost there...",
        "Running background tools...",
        "Decoding visual coordinates...",
        "Ek minute, research kar rahi hoon...",
        "Just give me a little time...",
        "Brainstorming solutions...",
        "Kuch hi seconds mein ready ho jayega...",
        "Scanning active window details..."
    ]
    property int currentPhraseIndex: 0
    property bool isVoiceMode: false
    property string voiceState: "listening"
    property string voiceTranscriptText: ""

    // ── THEME & AUDIO VISUALIZER ─────────────────
    property string themeName: "cyan"
    property string themeMainColor: "#00F5FF"
    property string themeSecColor: "#9B59F5"
    property real audioLevel: 0.0

    function changeTheme(theme) {
        var tName = theme.toLowerCase()
        themeName = tName
        if (tName === "gold" || tName === "jarvis") {
            themeMainColor = "#FFD700"
            themeSecColor = "#FF8C00"
        } else if (tName === "crimson" || tName === "red") {
            themeMainColor = "#FF3344"
            themeSecColor = "#FF0000"
        } else if (tName === "green" || tName === "matrix") {
            themeMainColor = "#00FF66"
            themeSecColor = "#008000"
        } else if (tName === "purple" || tName === "hermas") {
            themeMainColor = "#D000FF"
            themeSecColor = "#7F00FF"
        } else { // default cyan
            themeMainColor = "#00F5FF"
            themeSecColor = "#9B59F5"
        }
    }

    // ── GESTURE MIRRORING ─────────────────────────
    property bool userSmiling: false
    property bool userFrowning: false
    property bool userMouthOpen: false
    property bool userBlinking: false
    property bool userBrowsRaised: false
    property bool userHeadNod: false
    property bool userHeadShake: false
    property string userGesture: ""

    // ── GESTURE CONTROL STATE (from gesture_control.py) ──
    property bool ctrlEngaged: false      // fist-held -> real cursor control active
    property bool ctrlArmed: false        // fist detected, confirming hold
    property real ctrlCursorX: root.width / 2   // screen-space px
    property real ctrlCursorY: root.height / 2
    property string ctrlAction: "none"
    property var ctrlTrail: []            // [{x,y,a}] normalized 0..1
    property var ctrlBursts: []           // [{x,y,kind}] pending burst events

    property string stateText: "Ready"
    property color stateColor: "#00ff88"
    property string lastSentMsg: ""
    property string phaseIcon: ""
    property string phaseLabel: ""
    property bool gesturePointerVisible: false
    property real gesturePointerX: root.width / 2
    property real gesturePointerY: root.height / 2
    property bool gestureWasPinching: false
    property bool gestureWasGrabbing: false
    property int gestureSelectedBox: -1
    property real gestureGrabOffsetX: 0
    property real gestureGrabOffsetY: 0
    property var gestureStrokes: []
    property var gestureBoxes: []
    property var gestureActiveStroke: []
    property string gestureToastTitle: ""
    property string gestureToastBody: ""
    property bool gestureToastShown: false
    property bool gestureMirrorX: true

    // ── WINDOW VISIBILITY ────────────────────────
    property bool toolWindowShown: false
    property bool memoryWindowShown: false
    property bool phoneBridgeWindowShown: false
    property string phoneBridgeUrl: ""
    property string phoneBridgePin: ""
    property string phoneBridgeQr: ""
    property bool leftPanelShown: false
    property string consoleLog: ""

    // ── LAYOUT CONSTANTS ─────────────────────────
    readonly property int pad: 16
    readonly property int panelW: 220
    readonly property int dockH: 60
    readonly property int chatW: 520
    property int chatH: chatExpanded ? 540 : 340

    // ── LOAD SETTINGS ON STARTUP ────────────────
    function loadStartupSettings() {
        try {
            var s = JSON.parse(bridge.getSettings())
            autoDetectEnabled = s.location.auto_detect !== false
            gesturesEnabled = s.gestures ? (s.gestures.enabled !== false) : true
            autoScreenshotEnabled = s.screenshots ? (s.screenshots.auto_screenshot !== false) : true
            root.showAvatar = s.avatar ? (s.avatar.enabled !== false) : true
            var theme = (s.avatar && s.avatar.theme) ? s.avatar.theme : "cyan"
            root.changeTheme(theme)
            userLat = s.location.lat || 19.8762
            userLng = s.location.lng || 75.3704
            userLocation = s.location.city || "Detecting..."
            if (locationText) locationText.text = userLocation
            if (latInput) { latInput.text = userLat.toString(); latInput.deselect() }
            if (lngInput) { lngInput.text = userLng.toString(); lngInput.deselect() }
        } catch(e) {}
    }

    // ── MANUAL LOCATION ─────────────────────────
    function manualLocationChanged() {
        var lat = parseFloat(latInput.text)
        var lng = parseFloat(lngInput.text)
        if (!isNaN(lat) && !isNaN(lng)) {
            userLat = lat
            userLng = lng
            var settings = JSON.parse(bridge.getSettings())
            settings.location.lat = lat
            settings.location.lng = lng
            settings.location.auto_detect = false
            bridge.saveSettings(JSON.stringify(settings))
        }
    }

    Timer {
        id: hotspotTimer
        interval: 350
        repeat: false
        onTriggered: registerHotspots()
    }

    // Safety net: re-register hotspots periodically to catch any stale positions
    // from animations that finished between explicit registerHotspots() calls
    Timer {
        id: hotspotSafetyTimer
        interval: 3000
        repeat: true
        running: true
        onTriggered: registerHotspots()
    }

    Timer {
        id: talkingTimer
        interval: 3000
        repeat: false
        onTriggered: {
            if (isVoiceMode) {
                stateText = "Listening"
                stateColor = "#00FFFF"
                avatarState = "listening"
            }
        }
    }

    Timer {
        id: processingPhrasesTimer
        interval: 1800
        repeat: true
        running: isProcessing
        onTriggered: {
            var nextIndex = Math.floor(Math.random() * processingPhrases.length)
            if (nextIndex === currentPhraseIndex) {
                nextIndex = (nextIndex + 1) % processingPhrases.length
            }
            currentPhraseIndex = nextIndex
            processingStatusText = processingPhrases[currentPhraseIndex]
        }
        onRunningChanged: {
            if (running) {
                currentPhraseIndex = 0
                processingStatusText = "Working on it..."
            }
        }
    }

    // ── MODELS ───────────────────────────────────
    ListModel { id: memoryModel }
    ListModel { id: chatModel }
    ListModel { id: todoModel }
    ListModel { id: nodeModel }
    ListModel { id: attachedImagesModel }   // { "path": "file:///..." }
    ListModel { id: attachedTextsModel }    // { "preview": "...", "fullText": "..." }


    // ═══════════════════════════════════════════════
    //  HELPER FUNCTIONS
    // ═══════════════════════════════════════════════
    function registerHotspots() {
        bridge.clearHotspots()
        var widgets = []
        widgets.push(closeIrBtn)
        if (root.showAvatar && typeof iraAvatar !== "undefined" && iraAvatar && iraAvatar.visible) {
            widgets.push(iraAvatar)
        }
        if (rightPanelShown) widgets.push(rightPanel)
        else widgets.push(rightEdgeHandle)
        if (dockExpanded) {
            widgets.push(dock)
            if (chatPopupShown) widgets.push(chatPopup)
            if (attachedImagesModel.count + attachedTextsModel.count > 0) widgets.push(attachmentPreviewCard)
        } else {
            widgets.push(dockPill)
        }
        if (toolWindowShown) widgets.push(toolWindow)
        if (memoryWindowShown) widgets.push(memoryWindow)
        if (phoneBridgeWindowShown) widgets.push(phoneBridgeWindow)
        if (searchWindowShown) widgets.push(searchWindow)
        if (leftPanelShown) widgets.push(leftPanel)
        if (isVoiceMode) widgets.push(voiceOverlay)

        // When chat/sidebar is open, whole screen is a hotspot to catch click-outside
        if (chatPopupShown || rightPanelShown || leftPanelShown) {
            widgets.push(clickOutsideOverlay)
        }

        for (var i = 0; i < widgets.length; i++) {
            if (widgets[i] && widgets[i].visible) {
                var gp = widgets[i].mapToGlobal(0, 0)
                bridge.addHotspot(gp.x, gp.y, widgets[i].width, widgets[i].height)
            }
        }
        if (showNodes && typeof nodesContainer !== "undefined" && nodesContainer) {
            for (var j = 0; j < nodesContainer.children.length; j++) {
                var child = nodesContainer.children[j];
                if (child && child.visible && child.width > 0) {
                    var cg = child.mapToGlobal(0, 0)
                    bridge.addHotspot(cg.x, cg.y, child.width, child.height)
                }
            }
        }
    }

    function gestureScreenPoint(nx, ny) {
        var sx = gestureMirrorX ? (1.0 - nx) : nx
        return Qt.point(Math.max(0, Math.min(root.width, sx * root.width)),
                        Math.max(0, Math.min(root.height, ny * root.height)))
    }

    function showGestureToast(title, body) {
        gestureToastTitle = title
        gestureToastBody = body || ""
        gestureToastShown = true
        gestureToastTimer.restart()
    }

    function nearestGestureBox(px, py) {
        var best = -1
        var bestDist = 999999
        for (var i = 0; i < gestureBoxes.length; i++) {
            var b = gestureBoxes[i]
            var cx = b.x + b.w / 2
            var cy = b.y + b.h / 2
            var d = Math.abs(px - cx) + Math.abs(py - cy)
            if (d < bestDist && d < 220) {
                best = i
                bestDist = d
            }
        }
        return best
    }

    function updateGestureState(event) {
        var p = gestureScreenPoint(event.x || 0.5, event.y || 0.5)
        gesturePointerVisible = true
        gesturePointerX = p.x
        gesturePointerY = p.y

        if (event.pinch) {
            gestureActiveStroke.push({"x": p.x, "y": p.y})
            gestureCanvas.requestPaint()
        } else if (gestureWasPinching) {
            if (gestureActiveStroke.length > 1) {
                gestureStrokes.push(gestureActiveStroke)
            }
            gestureActiveStroke = []
            gestureCanvas.requestPaint()
        }
        gestureWasPinching = !!event.pinch

        if (event.grab) {
            if (!gestureWasGrabbing) {
                gestureSelectedBox = nearestGestureBox(p.x, p.y)
                if (gestureSelectedBox >= 0) {
                    var box = gestureBoxes[gestureSelectedBox]
                    gestureGrabOffsetX = p.x - box.x
                    gestureGrabOffsetY = p.y - box.y
                }
            }
            if (gestureSelectedBox >= 0) {
                var moved = gestureBoxes.slice()
                moved[gestureSelectedBox] = {
                    "x": Math.max(0, Math.min(root.width - moved[gestureSelectedBox].w, p.x - gestureGrabOffsetX)),
                    "y": Math.max(0, Math.min(root.height - moved[gestureSelectedBox].h, p.y - gestureGrabOffsetY)),
                    "w": moved[gestureSelectedBox].w,
                    "h": moved[gestureSelectedBox].h
                }
                gestureBoxes = moved
                gestureCanvas.requestPaint()
            }
        } else if (gestureWasGrabbing) {
            gestureSelectedBox = -1
        }
        gestureWasGrabbing = !!event.grab
    }

    function handleGestureOverlayEvent(jsonStr) {
        var event = JSON.parse(jsonStr)
        if (event.kind === "state") {
            updateGestureState(event)
            return
        }
        if (event.kind === "toast") {
            var label = event.name || "gesture"
            var body = event.action && event.action !== "none" ? ("action: " + event.action) : "detected"
            if (event.result && event.result.length > 0) body = event.result
            showGestureToast(label, body)
            if (event.name === "peace") {
                gestureBoxes.push({"x": Math.max(20, gesturePointerX - 80), "y": Math.max(20, gesturePointerY - 50), "w": 160, "h": 100})
                gestureCanvas.requestPaint()
            } else if (event.name === "open_palm") {
                gestureActiveStroke = []
                gestureStrokes = []
                gestureBoxes = []
                gestureCanvas.requestPaint()
            }
        }
    }


    function appendUserMessage(text, imgPath, largeTxt) {
        chatModel.append({
            "sender": "user",
            "text": text,
            "imagePath": imgPath,
            "largeText": largeTxt,
            "toolLogs": "",
            "isThinking": false,
            "toolName": "",
            "toolArgs": "",
            "toolResult": ""
        })
        chatListView.forceScrollToBottom()
    }

    function appendIraMessage() {
        chatModel.append({
            "sender": "ira",
            "text": "",
            "imagePath": "",
            "largeText": "",
            "toolLogs": "",
            "isThinking": true,
            "toolName": "",
            "toolArgs": "",
            "toolResult": ""
        })
        chatListView.forceScrollToBottom()
    }

    function appendThinkingMessage(thoughtText) {
        chatModel.append({
            "sender": "thinking",
            "text": thoughtText,
            "imagePath": "",
            "largeText": "",
            "toolLogs": "",
            "isThinking": false,
            "toolName": "",
            "toolArgs": "",
            "toolResult": ""
        })
        chatListView.forceScrollToBottom()
    }

    function updateThinkingMessage(thoughtText) {
        if (chatModel.count === 0 || chatModel.get(chatModel.count - 1).sender !== "thinking") {
            chatModel.append({
                "sender": "thinking",
                "text": thoughtText,
                "imagePath": "",
                "largeText": "",
                "toolLogs": "",
                "isThinking": false,
                "toolName": "",
                "toolArgs": "",
                "toolResult": ""
            })
            chatListView.forceScrollToBottom()
        } else {
            var idx = chatModel.count - 1
            chatModel.setProperty(idx, "text", thoughtText)
        }
    }

    function appendToolMessage(toolName, toolArgs) {
        chatModel.append({
            "sender": "tool",
            "text": "",
            "imagePath": "",
            "largeText": "",
            "toolLogs": "",
            "isThinking": false,
            "toolName": toolName,
            "toolArgs": toolArgs,
            "toolResult": ""
        })
        chatListView.forceScrollToBottom()
    }

    function updateLastToolResult(result) {
        for (var i = chatModel.count - 1; i >= 0; i--) {
            if (chatModel.get(i).sender === "tool") {
                chatModel.setProperty(i, "toolResult", result)
                break
            }
        }
    }

    function updateIraLogs(logText) {
        if (chatModel.count === 0 || chatModel.get(chatModel.count - 1).sender !== "ira") {
            chatModel.append({
                "sender": "ira",
                "text": "",
                "imagePath": "",
                "largeText": "",
                "toolLogs": logText,
                "isThinking": true,
                "toolName": "",
                "toolArgs": "",
                "toolResult": ""
            })
            chatListView.forceScrollToBottom()
        } else {
            var idx = chatModel.count - 1
            chatModel.setProperty(idx, "toolLogs", chatModel.get(idx).toolLogs + logText)
            chatModel.setProperty(idx, "isThinking", true)
        }
    }

    function updateIraTextChunk(partialHtml) {
        if (chatModel.count === 0 || chatModel.get(chatModel.count - 1).sender !== "ira") {
            chatModel.append({
                "sender": "ira",
                "text": partialHtml,
                "imagePath": "",
                "largeText": "",
                "toolLogs": "",
                "isThinking": true,
                "toolName": "",
                "toolArgs": "",
                "toolResult": ""
            })
            chatListView.forceScrollToBottom()
        } else {
            var idx = chatModel.count - 1
            chatModel.setProperty(idx, "text", partialHtml)
            chatModel.setProperty(idx, "isThinking", true)
        }
    }

    function finalizeIraMessage(responseHtml) {
        if (chatModel.count === 0 || chatModel.get(chatModel.count - 1).sender !== "ira") {
            chatModel.append({
                "sender": "ira",
                "text": responseHtml,
                "imagePath": "",
                "largeText": "",
                "toolLogs": "",
                "isThinking": false,
                "toolName": "",
                "toolArgs": "",
                "toolResult": ""
            })
            chatListView.forceScrollToBottom()
        } else {
            var idx = chatModel.count - 1
            var item = chatModel.get(idx)
            if (item.isThinking) {
                chatModel.setProperty(idx, "text", responseHtml)
                chatModel.setProperty(idx, "isThinking", false)
            } else {
                chatModel.append({
                    "sender": "ira",
                    "text": responseHtml,
                    "imagePath": "",
                    "largeText": "",
                    "toolLogs": "",
                    "isThinking": false,
                    "toolName": "",
                    "toolArgs": "",
                    "toolResult": ""
                })
                chatListView.forceScrollToBottom()
            }
        }
    }

    function getChatModelJson() {
        var list = [];
        for (var i = 0; i < chatModel.count; i++) {
            var item = chatModel.get(i);
            list.push({
                "sender": item.sender,
                "text": item.text,
                "imagePath": item.imagePath,
                "largeText": item.largeText,
                "toolLogs": item.toolLogs,
                "isThinking": item.isThinking,
                "toolName": item.toolName,
                "toolArgs": item.toolArgs,
                "toolResult": item.toolResult
            });
        }
        return JSON.stringify(list);
    }

    function getNodeModelJson() {
        var list = [];
        for (var i = 0; i < nodeModel.count; i++) {
            var item = nodeModel.get(i);
            list.push({
                "nodeId": item.nodeId,
                "title": item.title,
                "content": item.content,
                "nodeX": item.nodeX,
                "nodeY": item.nodeY,
                "nodeWidth": item.nodeWidth,
                "nodeHeight": item.nodeHeight,
                "zoomScale": item.zoomScale
            });
        }
        return JSON.stringify(list);
    }

    function sendMsg() {
        var text = inputField.text.trim()
        var hasImages = attachedImagesModel.count > 0
        var hasTexts = attachedTextsModel.count > 0
        if (text.length === 0 && !hasImages && !hasTexts) return
        if (isProcessing) return

        // Collect all image paths
        var imagePaths = []
        for (var i = 0; i < attachedImagesModel.count; i++) {
            imagePaths.push(attachedImagesModel.get(i).path)
        }
        // Collect all text chunks
        var textChunks = []
        var textPreview = ""
        for (var j = 0; j < attachedTextsModel.count; j++) {
            var t = attachedTextsModel.get(j)
            textChunks.push(t.fullText)
            textPreview += (j > 0 ? " | " : "") + t.preview
        }

        var imgPathVal = imagePaths.length > 0 ? JSON.stringify(imagePaths) : ""
        var txtVal = textChunks.length > 0 ? JSON.stringify(textChunks) : ""
        appendUserMessage(text, imgPathVal, txtVal)

        appendIraMessage()

        chatPopupShown = true

        bridge.sendMessage(text, JSON.stringify(imagePaths), JSON.stringify(textChunks))

        attachedImagesModel.clear()
        attachedTextsModel.clear()
        attachedImage = ""
        attachedLargeText = ""
        attachedLargeTextPreview = ""
        inputField.text = ""

        registerHotspots()
        hotspotTimer.start()
    }

    function stripHtml(html) {
        return html.replace(/<[^>]*>/g, '')
                   .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
                   .replace(/&amp;/g, '&').replace(/&quot;/g, '"')
                   .replace(/&#39;/g, "'").replace(/\n\s*\n/g, '\n').trim()
    }

    function getImageList(imagePath) {
        if (!imagePath) return []
        try {
            var parsed = JSON.parse(imagePath)
            if (Array.isArray(parsed)) return parsed
        } catch (e) {}
        return [imagePath]
    }

    function getTextList(largeText) {
        if (!largeText) return []
        try {
            var parsed = JSON.parse(largeText)
            if (Array.isArray(parsed)) return parsed
        } catch (e) {}
        return [largeText]
    }

    function truncateText(text, maxLen) {
        if (text.length <= maxLen) return text
        return text.substring(0, maxLen) + "…"
    }

    function activateWindow() {
        root.requestActivate()
    }

    // ═══════════════════════════════════════════════
    //  TOP CENTER: CLOSE IRA BUTTON
    // ═══════════════════════════════════════════════
    Rectangle {
        id: closeIrBtn
        x: root.width / 2 - 13; y: isBooting ? -40 : 5
        width: 26; height: 26; radius: 13
        color: closeIrMa.containsMouse ? Qt.rgba(1, 0, 0, 0.3) : Qt.rgba(0, 0, 0, 0.35)
        border.color: closeIrMa.containsMouse ? Qt.rgba(1, 0.27, 0.27, 0.6) : Qt.rgba(1, 0.27, 0.27, 0.3)
        border.width: 1
        z: 50
        opacity: isBooting ? 0 : (closeIrMa.containsMouse ? 1.0 : 0.5)
        scale: isBooting ? 0.5 : 1.0

        Text {
            anchors.centerIn: parent
            text: "✕"
            color: "#FF4444"
            font { pixelSize: 11; bold: true }
        }

        MouseArea {
            id: closeIrMa
            anchors.fill: parent
            hoverEnabled: true
            onClicked: {
                bridge.playSound("click")
                bridge.hideHUD(getChatModelJson(), getNodeModelJson())
            }
        }

        Behavior on y { NumberAnimation { duration: 600; easing.type: Easing.OutBack; easing.amplitude: 1.5 } }
        Behavior on opacity { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
        Behavior on scale {
            NumberAnimation { duration: 800; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.6 }
        }
    }

    // ═══════════════════════════════════════════════
    // ═══════════════════════════════════════════════
    //  IRA AVATAR — Procedural Anime Girl (center)
    // ═══════════════════════════════════════════════
    IraAvatar {
        id: iraAvatar
        property real customX: -1
        property real customY: -1

        mainThemeColor: root.themeMainColor
        secThemeColor: root.themeSecColor

        x: customX >= 0 ? customX : ((chatPopupShown && dockExpanded) ? Math.max(20, (root.width / 2 - chatW / 2) / 2 - width / 2) : (dockExpanded ? (root.width - width) / 2 : (root.width - width - 20)))
        y: customY >= 0 ? customY : ((chatPopupShown && dockExpanded) ? (root.height / 2 - height / 2 - 40) : (dockExpanded ? 40 : 20))
        width: (chatPopupShown && dockExpanded) ? (root.height * 0.45) : (dockExpanded ? (root.height - 200) : 80)
        height: (chatPopupShown && dockExpanded) ? (root.height * 0.45) : (dockExpanded ? (root.height - 200) : 80)
        z: 2
        visible: root.showAvatar
        opacity: isBooting ? 0 : root.avatarOpacity
        scale: isBooting ? 0.3 : 1.0
        avatarState: root.avatarState
        mouseX: root.mouseX
        mouseY: root.mouseY
        userSmiling: root.userSmiling
        userFrowning: root.userFrowning
        userMouthOpen: root.userMouthOpen
        userBlinking: root.userBlinking
        userBrowsRaised: root.userBrowsRaised
        userHeadNod: root.userHeadNod
        userHeadShake: root.userHeadShake
        userGesture: root.userGesture

        MouseArea {
            id: avatarInteractiveArea
            anchors.fill: parent
            hoverEnabled: true

            // Drag support
            property real dragStartX: 0
            property real dragStartY: 0
            property bool isDragging: false

            onPressed: (mouse) => {
                dragStartX = mouse.x
                dragStartY = mouse.y
                isDragging = false
            }

            onPositionChanged: (mouse) => {
                if (pressed) {
                    var dx = mouse.x - dragStartX
                    var dy = mouse.y - dragStartY
                    if (Math.abs(dx) > 5 || Math.abs(dy) > 5 || isDragging) {
                        isDragging = true
                        var targetX = parent.x + dx
                        var targetY = parent.y + dy
                        // Keep within screen bounds
                        targetX = Math.max(0, Math.min(root.width - parent.width, targetX))
                        targetY = Math.max(0, Math.min(root.height - parent.height, targetY))
                        parent.customX = targetX
                        parent.customY = targetY
                    }
                }
            }

            onReleased: {
                if (isDragging) {
                    registerHotspots() // update clickthrough hotspots for new position
                }
            }

            onDoubleClicked: {
                parent.customX = -1
                parent.customY = -1
                bridge.playSound("collapse")
                registerHotspots()
            }

            onClicked: (mouse) => {
                if (isDragging) return
                // Touch reaction logic:
                // Click top 45% (head area): good touch / headpat
                // Click bottom 55% (body area): tease / tickle
                var clickedYRatio = mouse.y / height
                if (clickedYRatio < 0.45) {
                    bridge.playSound("success")
                    bridge.triggerReaction("headpat")
                } else {
                    bridge.playSound("click")
                    bridge.triggerReaction("tickle")
                }
            }
        }

        Behavior on x { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }
        Behavior on y { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }
        Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }
        Behavior on height { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }
        Behavior on opacity { NumberAnimation { duration: 800; easing.type: Easing.OutCubic } }
        Behavior on scale {
            NumberAnimation { duration: 1200; easing.type: Easing.OutElastic; easing.amplitude: 1.2; easing.period: 0.5 }
        }

        // Cinematic entrance glow ring
        Rectangle {
            id: avatarGlowRing
            anchors.centerIn: parent
            width: parent.width + 40
            height: parent.height + 40
            radius: width / 2
            color: "transparent"
            border.color: "#00FFFF"
            border.width: 2
            opacity: 0
            z: -1

            SequentialAnimation {
                id: avatarGlowAnim
                running: false
                NumberAnimation { target: avatarGlowRing; property: "opacity"; from: 0; to: 0.6; duration: 400 }
                NumberAnimation { target: avatarGlowRing; property: "width"; from: 50; to: iraAvatar.width + 80; duration: 1000; easing.type: Easing.OutQuad }
                NumberAnimation { target: avatarGlowRing; property: "height"; from: 50; to: iraAvatar.height + 80; duration: 1000; easing.type: Easing.OutQuad }
                NumberAnimation { target: avatarGlowRing; property: "opacity"; from: 0.6; to: 0; duration: 600 }
            }
        }

        // Real-time Audio Visualizer Rings (behind Avatar)
        Rectangle {
            id: visualizerRing
            anchors.centerIn: iraAvatar
            width: iraAvatar.width + 30 + (root.audioLevel * 100)
            height: iraAvatar.height + 30 + (root.audioLevel * 100)
            radius: width / 2
            color: "transparent"
            border.color: root.themeMainColor
            border.width: 1.5 + (root.audioLevel * 4)
            opacity: root.isVoiceMode ? (0.2 + root.audioLevel * 0.8) : 0
            z: 1 // avatar is z: 2, so this sits right behind it
            visible: root.showAvatar && root.isVoiceMode

            Behavior on width { NumberAnimation { duration: 60; easing.type: Easing.OutCubic } }
            Behavior on height { NumberAnimation { duration: 60; easing.type: Easing.OutCubic } }
            Behavior on border.width { NumberAnimation { duration: 60; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
        }

        Rectangle {
            id: visualizerRingOuter
            anchors.centerIn: iraAvatar
            width: iraAvatar.width + 60 + (root.audioLevel * 180)
            height: iraAvatar.height + 60 + (root.audioLevel * 180)
            radius: width / 2
            color: "transparent"
            border.color: root.themeSecColor
            border.width: 1.0
            opacity: root.isVoiceMode ? (0.1 + root.audioLevel * 0.5) : 0
            z: 1 // behind avatar
            visible: root.showAvatar && root.isVoiceMode

            Behavior on width { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
            Behavior on height { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        }
    }

    Binding {
        target: root
        property: "avatarOpacity"
        value: {
            if (!dockExpanded) return 0.20
            if (chatPopupShown) return 0.85
            if (rightPanelShown || leftPanelShown || toolWindowShown || memoryWindowShown || searchWindowShown) return 0.35
            return 0.85
        }
    }

    Canvas {
        id: gestureCanvas
        anchors.fill: parent
        z: 4
        visible: gestureStrokes.length > 0 || gestureActiveStroke.length > 0 || gestureBoxes.length > 0 || gesturePointerVisible
        opacity: 0.95
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.shadowColor = "rgba(0, 255, 255, 0.55)"
            ctx.shadowBlur = 14
            ctx.strokeStyle = "rgba(0, 255, 255, 0.88)"
            ctx.lineWidth = 4
            function drawStroke(points) {
                if (!points || points.length < 2) return
                ctx.beginPath()
                ctx.moveTo(points[0].x, points[0].y)
                for (var i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y)
                ctx.stroke()
            }
            for (var s = 0; s < gestureStrokes.length; s++) drawStroke(gestureStrokes[s])
            drawStroke(gestureActiveStroke)
            ctx.shadowBlur = 18
            for (var b = 0; b < gestureBoxes.length; b++) {
                var box = gestureBoxes[b]
                ctx.strokeStyle = b === gestureSelectedBox ? "rgba(0, 255, 136, 0.95)" : "rgba(0, 180, 255, 0.85)"
                ctx.lineWidth = 2
                ctx.strokeRect(box.x, box.y, box.w, box.h)
                ctx.fillStyle = "rgba(0, 40, 60, 0.16)"
                ctx.fillRect(box.x, box.y, box.w, box.h)
            }
        }
    }

    // ═══════════════════════════════════════════════
    //  GESTURE CONTROL — comet trail + engage ring + burst FX
    //  (driven by gestureControlState from gesture_control.py)
    // ═══════════════════════════════════════════════
    Canvas {
        id: ctrlTrailCanvas
        anchors.fill: parent
        z: 44
        // Visible whenever we have a trail OR a live pointer
        visible: gesturePointerVisible && (ctrlTrail.length > 0 || ctrlEngaged)
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            var pts = ctrlTrail
            if (pts.length < 2) return
            ctx.lineCap = "round"
            ctx.lineJoin = "round"

            // Glow underlay — thick translucent, theme main color
            for (var i = 1; i < pts.length; i++) {
                var p0 = pts[i - 1], p1 = pts[i]
                var a = (p1.a + p0.a) * 0.5
                ctx.strokeStyle = Qt.rgba(0.0, 0.96, 1.0, a * 0.25)
                ctx.lineWidth = 18 * a + 4
                ctx.beginPath()
                ctx.moveTo(p0.x * width, p0.y * height)
                ctx.lineTo(p1.x * width, p1.y * height)
                ctx.stroke()
            }
            // Crisp core — tapering width by age, like a comet tail
            for (var j = 1; j < pts.length; j++) {
                var q0 = pts[j - 1], q1 = pts[j]
                var ag = (q1.a + q0.a) * 0.5
                ctx.strokeStyle = Qt.rgba(1.0, 1.0, 1.0, ag)
                ctx.lineWidth = 5 * ag + 1
                ctx.beginPath()
                ctx.moveTo(q0.x * width, q0.y * height)
                ctx.lineTo(q1.x * width, q1.y * height)
                ctx.stroke()
            }
        }
        // Repaint whenever the trail or engage changes
        Connections {
            target: root
            function onCtrlTrailChanged() { ctrlTrailCanvas.requestPaint() }
        }
    }

    // Burst layer — radial particle explosions on click / engage
    Repeater {
        id: ctrlBurstLayer
        model: ctrlBursts
        delegate: Item {
            // Each burst spawns 8 particles around its center.
            property real bx: modelData.x * root.width
            property real by: modelData.y * root.height
            property string bkind: modelData.kind || "click"
            x: bx; y: by; z: 46
            Repeater {
                model: 8
                Rectangle {
                    property real ang: index * (Math.PI / 4)
                    property real dist: 0
                    width: 8; height: 8; radius: 4
                    color: bkind === "engage" ? root.themeSecColor : root.themeMainColor
                    x: Math.cos(ang) * dist - width / 2
                    y: Math.sin(ang) * dist - height / 2
                    opacity: 1.0
                    SequentialAnimation on dist {
                        running: true
                        NumberAnimation { from: 6; to: 54; duration: 300; easing.type: Easing.OutCubic }
                        NumberAnimation { from: 54; to: 70; duration: 200; easing.type: Easing.OutQuad }
                    }
                    SequentialAnimation on opacity {
                        running: true
                        NumberAnimation { from: 1.0; to: 0.0; duration: 480; easing.type: Easing.OutQuad }
                    }
                }
            }
        }
    }

    // Engage ring — dual neon pulsing ring around the fingertip when ENGAGED,
    // small armed dot while fist is being confirmed.
    Item {
        id: ctrlEngageRing
        x: ctrlCursorX; y: ctrlCursorY
        z: 45
        visible: gesturePointerVisible && (ctrlEngaged || ctrlArmed)
        // Outer pulsing ring (theme main color)
        Rectangle {
            anchors.centerIn: parent
            width: ctrlEngaged ? 46 : 20; height: width; radius: width / 2
            color: "transparent"
            border.color: ctrlEngaged ? root.themeMainColor : Qt.rgba(1, 1, 1, 0.35)
            border.width: ctrlEngaged ? 3 : 2
            opacity: ctrlEngaged ? 1.0 : 0.6
            SequentialAnimation on scale {
                running: ctrlEngaged; loops: Animation.Infinite
                NumberAnimation { from: 1.0; to: 1.18; duration: 480; easing.type: Easing.OutCubic }
                NumberAnimation { from: 1.18; to: 1.0; duration: 480; easing.type: Easing.OutCubic }
            }
            Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        }
        // Inner counter-rotating ring (theme sec color)
        Rectangle {
            anchors.centerIn: parent
            width: ctrlEngaged ? 30 : 10; height: width; radius: width / 2
            color: "transparent"
            border.color: ctrlEngaged ? root.themeSecColor : "transparent"
            border.width: ctrlEngaged ? 2 : 0
            opacity: ctrlEngaged ? 0.9 : 0
            SequentialAnimation on scale {
                running: ctrlEngaged; loops: Animation.Infinite
                NumberAnimation { from: 1.2; to: 0.82; duration: 600; easing.type: Easing.OutCubic }
                NumberAnimation { from: 0.82; to: 1.2; duration: 600; easing.type: Easing.OutCubic }
            }
            Behavior on opacity { NumberAnimation { duration: 120 } }
        }
        // Center dot — always visible while pointer is live
        Rectangle {
            anchors.centerIn: parent
            width: 5; height: 5; radius: 2.5
            color: ctrlEngaged ? "#FFFFFF" : root.themeMainColor
        }
    }

    Rectangle {
        id: gestureReticle
        width: gestureWasPinching ? 34 : 24
        height: width
        radius: width / 2
        x: gesturePointerX - width / 2
        y: gesturePointerY - height / 2
        z: 45
        visible: gesturePointerVisible
        color: "transparent"
        border.width: gestureWasPinching ? 3 : 2
        border.color: gestureWasPinching ? "#00FF88" : "#00FFFF"
        opacity: 0.9
        Rectangle {
            anchors.centerIn: parent
            width: 4
            height: 4
            radius: 2
            color: parent.border.color
        }
    }

    Rectangle {
        id: gestureToast
        width: Math.min(360, root.width - 40)
        height: 58
        radius: 10
        x: root.width / 2 - width / 2
        y: 48
        z: 60
        visible: gestureToastShown
        opacity: gestureToastShown ? 1 : 0
        color: Qt.rgba(0.0, 0.04, 0.08, 0.88)
        border.color: Qt.rgba(0.0, 1.0, 1.0, 0.42)
        border.width: 1
        Column {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 3
            Text {
                width: parent.width
                text: gestureToastTitle
                color: "#00FFFF"
                font { family: "Consolas"; pixelSize: 14; bold: true }
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: gestureToastBody
                color: Qt.rgba(1, 1, 1, 0.78)
                font { family: "Segoe UI"; pixelSize: 12 }
                elide: Text.ElideRight
            }
        }
        Behavior on opacity { NumberAnimation { duration: 160 } }
    }

    // ═══════════════════════════════════════════════
    //  CLICK-OUTSIDE OVERLAY — closes chat/sidebar
    // ═══════════════════════════════════════════════
    Rectangle {
        id: clickOutsideOverlay
        anchors.fill: parent
        color: "transparent"
        visible: chatPopupShown || rightPanelShown || leftPanelShown || searchWindowShown
        z: 5

        MouseArea {
            anchors.fill: parent
            onClicked: {
                if (chatPopupShown) { chatPopupShown = false; registerHotspots(); hotspotTimer.start() }
                if (rightPanelShown) { rightPanelShown = false; registerHotspots(); hotspotTimer.start() }
                if (leftPanelShown) { leftPanelShown = false; registerHotspots(); hotspotTimer.start() }
                if (searchWindowShown) { searchWindowShown = false }
            }
        }
    }

    // ═══════════════════════════════════════════════
    //  RIGHT SIDEBAR — COMMAND CENTER (scrollable)
    // ═══════════════════════════════════════════════
    // ═══════════════════════════════════════════════
    //  LEFT SIDEBAR — LOGS & GESTURE CONTROL CENTER
    // ═══════════════════════════════════════════════
    Rectangle {
        id: leftPanel
        x: leftPanelShown ? pad : -panelW - 5
        y: pad + 8
        width: panelW
        height: root.height - y - (dockExpanded ? (dockH + bottomMargin + 12) : (bottomMargin + 12))
        radius: 12
        color: Qt.rgba(0, 0.024, 0.059, 0.9)
        border.color: Qt.rgba(0, 0.5, 1, 0.18); border.width: 1
        clip: true; visible: x > -panelW - 5; z: 10

        Behavior on x { NumberAnimation { duration: 280; easing.type: Easing.InOutQuad } }

        // Auto-scroll on new content
        Connections {
            target: root
            function onConsoleLogChanged() {
                leftConsoleFlick.contentY = Math.max(0, leftConsoleText.height - leftConsoleFlick.height)
            }
        }

        // ── HEADER ──
        Rectangle {
            id: leftHeader
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 36; color: "transparent"
            z: 5

            RowLayout {
                anchors { fill: parent; leftMargin: 12; rightMargin: 8 }
                spacing: 8

                Text {
                    text: "📊 LOGS & GESTURE"
                    color: "#00FF88"
                    font { pixelSize: 10; family: "Consolas"; bold: true; letterSpacing: 1 }
                }

                Item { Layout.fillWidth: true }

                Rectangle {
                    width: 18; height: 18; radius: 4
                    color: closeLeftMa.containsMouse ? Qt.rgba(1, 0.27, 0.27, 0.2) : "transparent"
                    Text { anchors.centerIn: parent; text: "✕"; color: Qt.rgba(1, 0.27, 0.27, 0.6); font.pixelSize: 9 }
                    MouseArea { id: closeLeftMa; anchors.fill: parent; hoverEnabled: true; onClicked: { activateWindow(); leftPanelShown = false; registerHotspots(); hotspotTimer.start() } }
                }
            }
        }

        Rectangle {
            id: leftHeaderDiv
            anchors { top: leftHeader.bottom; left: parent.left; right: parent.right }
            height: 1; color: Qt.rgba(0, 1, 1, 0.08)
        }

        ColumnLayout {
            anchors { top: leftHeaderDiv.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10 }
            spacing: 10

            // 1. CONSOLE LOGS VIEW (Upper Section)
            Text {
                text: "SYSTEM TERMINAL LOG"
                color: Qt.rgba(0, 1, 0.5, 0.35)
                font { pixelSize: 7; family: "Consolas"; bold: true; letterSpacing: 1.5 }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: Qt.rgba(0, 0, 0, 0.35)
                border.color: Qt.rgba(0, 1, 1, 0.1); border.width: 1
                radius: 8
                clip: true

                Flickable {
                    id: leftConsoleFlick
                    anchors.fill: parent; anchors.margins: 8
                    contentHeight: leftConsoleText.height
                    clip: true
                    flickableDirection: Flickable.VerticalFlick

                    TextEdit {
                        id: leftConsoleText
                        width: leftConsoleFlick.width
                        text: root.consoleLog
                        color: "#00FF88"
                        font { family: "Consolas"; pixelSize: 9 }
                        wrapMode: TextEdit.Wrap
                        readOnly: true
                        selectByMouse: true
                    }

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                        contentItem: Rectangle {
                            implicitWidth: 3; radius: 1.5
                            color: Qt.rgba(0, 1, 0.5, 0.2)
                        }
                    }
                }
            }

            // 2. CAMERA & GESTURE STATUS (Lower Section)
            Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(0, 1, 1, 0.08) }

            Text {
                text: "GESTURE CAMERA VIEW"
                color: Qt.rgba(0, 1, 0.5, 0.35)
                font { pixelSize: 7; family: "Consolas"; bold: true; letterSpacing: 1.5 }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 140
                color: Qt.rgba(0, 0, 0, 0.4)
                border.color: Qt.rgba(0, 1, 1, 0.1); border.width: 1
                radius: 8
                clip: true

                Image {
                    id: leftCameraPreview
                    anchors.fill: parent; anchors.margins: 2
                    fillMode: Image.PreserveAspectFit
                    source: cameraFrameBase64.length > 0 ? "data:image/jpeg;base64," + cameraFrameBase64 : ""
                    visible: cameraFrameBase64.length > 0
                }

                Column {
                    anchors.centerIn: parent
                    visible: cameraFrameBase64.length === 0
                    spacing: 4
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "📷"; font.pixelSize: 22; opacity: 0.2 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Camera feed waiting..."; color: Qt.rgba(0, 1, 1, 0.15); font { pixelSize: 8; family: "Consolas" } }
                }

                // Camera status dot
                Rectangle {
                    anchors { top: parent.top; right: parent.right; margins: 6 }
                    width: 6; height: 6; radius: 3
                    color: cameraFrameBase64.length > 0 ? "#00FF88" : "#FF4444"
                }
            }

            // 3. GESTURE CONTROLS
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 24
                spacing: 8

                Text {
                    text: "GESTURE ENGINE"
                    color: Qt.rgba(0, 1, 1, 0.4)
                    font { pixelSize: 8; family: "Consolas" }
                    Layout.fillWidth: true
                }

                Rectangle {
                    width: 32; height: 16; radius: 8
                    color: gesturesEnabled ? "#00FF88" : "#333"
                    border.color: Qt.rgba(0, 1, 1, 0.15); border.width: 1

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            gesturesEnabled = !gesturesEnabled
                            var settings = JSON.parse(bridge.getSettings())
                            if (!settings.gestures) settings.gestures = {}
                            settings.gestures.enabled = gesturesEnabled
                            bridge.saveSettings(JSON.stringify(settings))
                            if (gesturesEnabled) {
                                bridge.runCommandAsync("python gesture_control.py")
                            } else {
                                bridge.runCommandAsync("taskkill /f /im python.exe /fi \"windowtitle eq gesture_control*\"")
                            }
                        }
                    }
                    Rectangle {
                        x: gesturesEnabled ? 17 : 1
                        width: 14; height: 14; radius: 7
                        color: "white"
                        Behavior on x { NumberAnimation { duration: 120 } }
                    }
                }
            }

            // 4. ACTIVE AI MODELS
            Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(0, 1, 1, 0.08) }

            Text {
                text: "ACTIVE AI MODELS"
                color: Qt.rgba(0, 1, 0.5, 0.35)
                font { pixelSize: 7; family: "Consolas"; bold: true; letterSpacing: 1.5 }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 88
                color: Qt.rgba(0, 0, 0, 0.25)
                border.color: Qt.rgba(0, 1, 1, 0.08); border.width: 1
                radius: 8

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 8
                    spacing: 4

                     RowLayout {
                        Text { text: "Main Agent:"; color: "#00FFFF"; font.family: "Consolas"; font.pixelSize: 8; font.bold: true; Layout.preferredWidth: 65 }
                        Text { text: root.activeModels.main_agent || "Loading..."; color: "#FFFFFF"; font.family: "Consolas"; font.pixelSize: 8 }
                    }
                    RowLayout {
                        Text { text: "Live Voice:"; color: "#00FFFF"; font.family: "Consolas"; font.pixelSize: 8; font.bold: true; Layout.preferredWidth: 65 }
                        Text { text: root.activeModels.live_voice || "Loading..."; color: "#FFFFFF"; font.family: "Consolas"; font.pixelSize: 8 }
                    }
                    RowLayout {
                        Text { text: "Image/Video:"; color: "#00FFFF"; font.family: "Consolas"; font.pixelSize: 8; font.bold: true; Layout.preferredWidth: 65 }
                        Text { text: (root.activeModels.image_gen || "") + " / " + (root.activeModels.video_gen || ""); color: "#FFFFFF"; font.family: "Consolas"; font.pixelSize: 8 }
                    }
                    RowLayout {
                        Text { text: "Music/TTS:"; color: "#00FFFF"; font.family: "Consolas"; font.pixelSize: 8; font.bold: true; Layout.preferredWidth: 65 }
                        Text { text: (root.activeModels.music_gen || "") + " / " + (root.activeModels.tts_voice || ""); color: "#FFFFFF"; font.family: "Consolas"; font.pixelSize: 8 }
                    }
                }
            }
        }
    }

    Rectangle {
        id: rightPanel
        x: rightPanelShown ? (root.width - panelW - pad) : root.width + 5
        y: pad + 8
        width: panelW
        height: root.height - y - (dockExpanded ? (dockH + bottomMargin + 12) : (bottomMargin + 12))
        radius: 12
        color: Qt.rgba(0, 0.024, 0.059, 0.9)
        border.color: Qt.rgba(0, 0.5, 1, 0.18); border.width: 1
        clip: true; visible: x < root.width + 5; z: 10

        Behavior on x { NumberAnimation { duration: 280; easing.type: Easing.InOutQuad } }

        // ── HEADER ──
        Rectangle {
            id: rightHeader
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 36; color: "transparent"
            z: 5

            RowLayout {
                anchors { fill: parent; leftMargin: 12; rightMargin: 8 }
                spacing: 8

                // Reactor core indicator
                Rectangle {
                    width: 20; height: 20; radius: 10
                    color: Qt.rgba(0, 0.05, 0.1, 0.9)
                    border.color: stateColor; border.width: 1.5

                    Rectangle {
                        anchors.centerIn: parent
                        width: 8; height: 8; radius: 4
                        color: stateColor
                        SequentialAnimation on opacity {
                            running: true; loops: Animation.Infinite
                            NumberAnimation { from: 0.5; to: 1.0; duration: 800 }
                            NumberAnimation { from: 1.0; to: 0.5; duration: 800 }
                        }
                    }
                }

                Text {
                    text: "IRA"
                    color: "#00FFFF"
                    font { pixelSize: 10; family: "Consolas"; bold: true; letterSpacing: 2 }
                }

                Rectangle { width: 1; height: 14; color: Qt.rgba(0, 1, 1, 0.15) }

                Text {
                    text: isProcessing ? processingStatusText : stateText
                    color: Qt.rgba(0, 1, 1, 0.5)
                    font { pixelSize: 8; family: "Consolas" }
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Rectangle {
                    width: 18; height: 18; radius: 4
                    color: closeRightMa.containsMouse ? Qt.rgba(1, 0.27, 0.27, 0.2) : "transparent"
                    Text { anchors.centerIn: parent; text: "✕"; color: Qt.rgba(1, 0.27, 0.27, 0.6); font.pixelSize: 9 }
                    MouseArea { id: closeRightMa; anchors.fill: parent; hoverEnabled: true; onClicked: { activateWindow(); rightPanelShown = false; registerHotspots(); hotspotTimer.start() } }
                }
            }
        }

        Rectangle {
            anchors { top: rightHeader.bottom; left: parent.left; right: parent.right }
            height: 1; color: Qt.rgba(0, 1, 1, 0.08)
        }

        // ── SCROLLABLE CONTENT ──
        Flickable {
            id: rightScroll
            anchors { top: rightHeader.bottom; topMargin: 4; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10 }
            contentHeight: rightContent.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                contentItem: Rectangle {
                    implicitWidth: 3; radius: 1
                    color: Qt.rgba(0, 1, 1, 0.2)
                }
            }

            ColumnLayout {
                id: rightContent
                width: parent.width
                spacing: 10

                // ── SYSTEM STATUS ──
                Rectangle {
                    Layout.fillWidth: true; height: 72; radius: 8
                    color: Qt.rgba(0, 0, 0, 0.25)
                    border.color: Qt.rgba(0, 1, 1, 0.1); border.width: 1

                    ColumnLayout {
                        anchors { fill: parent; margins: 8 }
                        spacing: 4

                        Text {
                            text: "SYSTEM STATUS"
                            color: Qt.rgba(0, 1, 1, 0.35)
                            font { pixelSize: 7; family: "Consolas"; bold: true; letterSpacing: 2 }
                        }

                        RowLayout {
                            spacing: 10
                            ColumnLayout {
                                spacing: 1
                                Text { text: "CPU"; color: Qt.rgba(0, 1, 1, 0.25); font { pixelSize: 7; family: "Consolas" } }
                                Text { text: cpuVal.toFixed(0) + "%"; color: cpuVal > 80 ? "#FF4444" : "#0080FF"; font { pixelSize: 11; family: "Consolas"; bold: true } }
                            }
                            ColumnLayout {
                                spacing: 1
                                Text { text: "RAM"; color: Qt.rgba(0, 1, 1, 0.25); font { pixelSize: 7; family: "Consolas" } }
                                Text { text: ramVal.toFixed(0) + "%"; color: Qt.rgba(0, 1, 1, 0.55); font { pixelSize: 11; family: "Consolas"; bold: true } }
                            }
                            ColumnLayout {
                                spacing: 1
                                visible: batVal > 0
                                Text { text: "BAT"; color: Qt.rgba(0, 1, 1, 0.25); font { pixelSize: 7; family: "Consolas" } }
                                Text { text: batVal.toFixed(0) + "%" + (isCharging ? " ⚡" : ""); color: Qt.rgba(0, 1, 1, 0.55); font { pixelSize: 11; family: "Consolas"; bold: true } }
                            }
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(0, 1, 1, 0.06) }

                // ── SETTINGS ──
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: settingsContent.implicitHeight + 16
                    radius: 8
                    color: Qt.rgba(0, 0, 0, 0.25)
                    border.color: Qt.rgba(0, 1, 1, 0.1); border.width: 1

                    ColumnLayout {
                        id: settingsContent
                        x: 8; y: 8
                        width: parent.width - 16
                        spacing: 6

                        Text {
                            text: "SETTINGS"
                            color: Qt.rgba(0, 1, 1, 0.35)
                            font { pixelSize: 7; family: "Consolas"; bold: true; letterSpacing: 2 }
                        }

                        // Location display
                        RowLayout {
                            spacing: 6
                            Layout.fillWidth: true
                            Text { text: "📍"; font.pixelSize: 10 }
                            ColumnLayout {
                                spacing: 1
                                Layout.fillWidth: true
                                Text { text: "Location"; color: Qt.rgba(0, 1, 1, 0.25); font { pixelSize: 7; family: "Consolas" } }
                                Text {
                                    id: locationText
                                    text: "Detecting..."
                                    color: "#00d4ff"
                                    font { pixelSize: 8; family: "Consolas" }
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                    wrapMode: Text.WrapAnywhere
                                    maximumLineCount: 2
                                }
                            }
                        }

                        // Auto-detect toggle
                        RowLayout {
                            spacing: 8
                            Layout.fillWidth: true
                            Text { text: "Auto-detect"; color: Qt.rgba(0, 1, 1, 0.4); font { pixelSize: 8; family: "Consolas" } }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                width: 36; height: 18; radius: 9
                                color: autoDetectEnabled ? "#00ff88" : "#333"
                                border.color: Qt.rgba(0, 1, 1, 0.15); border.width: 1

                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        autoDetectEnabled = !autoDetectEnabled
                                        // Save settings via bridge
                                        var settings = JSON.parse(bridge.getSettings())
                                        settings.location.auto_detect = autoDetectEnabled
                                        bridge.saveSettings(JSON.stringify(settings))
                                    }
                                }
                                Rectangle {
                                    x: autoDetectEnabled ? 19 : 1
                                    width: 16; height: 16; radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }

                        // Gestures toggle
                        RowLayout {
                            spacing: 8
                            Layout.fillWidth: true
                            Text { text: "Gestures (Hand/Face)"; color: Qt.rgba(0, 1, 1, 0.4); font { pixelSize: 8; family: "Consolas" } }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                width: 36; height: 18; radius: 9
                                color: gesturesEnabled ? "#00ff88" : "#333"
                                border.color: Qt.rgba(0, 1, 1, 0.15); border.width: 1

                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        gesturesEnabled = !gesturesEnabled
                                        // Save settings via bridge
                                        var settings = JSON.parse(bridge.getSettings())
                                        if (!settings.gestures) settings.gestures = {}
                                        settings.gestures.enabled = gesturesEnabled
                                        bridge.saveSettings(JSON.stringify(settings))
                                    }
                                }
                                Rectangle {
                                    x: gesturesEnabled ? 19 : 1
                                    width: 16; height: 16; radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }

                        // Auto-screenshot toggle
                        RowLayout {
                            spacing: 8
                            Layout.fillWidth: true
                            Text { text: "Auto Screenshot"; color: Qt.rgba(0, 1, 1, 0.4); font { pixelSize: 8; family: "Consolas" } }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                width: 36; height: 18; radius: 9
                                color: autoScreenshotEnabled ? "#00ff88" : "#333"
                                border.color: Qt.rgba(0, 1, 1, 0.15); border.width: 1

                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        autoScreenshotEnabled = !autoScreenshotEnabled
                                        var settings = JSON.parse(bridge.getSettings())
                                        if (!settings.screenshots) settings.screenshots = {}
                                        settings.screenshots.auto_screenshot = autoScreenshotEnabled
                                        bridge.saveSettings(JSON.stringify(settings))
                                    }
                                }
                                Rectangle {
                                    x: autoScreenshotEnabled ? 19 : 1
                                    width: 16; height: 16; radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }

                        // Manual location input (shown when auto-detect is off)
                        ColumnLayout {
                            visible: !autoDetectEnabled
                            spacing: 4
                            Layout.fillWidth: true

                            RowLayout {
                                spacing: 6
                                Layout.fillWidth: true
                                Text { text: "Lat:"; color: Qt.rgba(0, 1, 1, 0.3); font { pixelSize: 8; family: "Consolas" } }
                                Rectangle {
                                    Layout.fillWidth: true; height: 20; radius: 4
                                    color: Qt.rgba(0, 0, 0, 0.3)
                                    border.color: Qt.rgba(0, 1, 1, 0.1); border.width: 1
                                    TextInput {
                                        id: latInput
                                        anchors { fill: parent; margins: 4 }
                                        color: "#00d4ff"
                                        font { pixelSize: 9; family: "Consolas" }
                                        verticalAlignment: Text.AlignVCenter
                                        onTextChanged: manualLocationChanged()
                                    }
                                }
                            }

                            RowLayout {
                                spacing: 6
                                Layout.fillWidth: true
                                Text { text: "Lng:"; color: Qt.rgba(0, 1, 1, 0.3); font { pixelSize: 8; family: "Consolas" } }
                                Rectangle {
                                    Layout.fillWidth: true; height: 20; radius: 4
                                    color: Qt.rgba(0, 0, 0, 0.3)
                                    border.color: Qt.rgba(0, 1, 1, 0.1); border.width: 1
                                    TextInput {
                                        id: lngInput
                                        anchors { fill: parent; margins: 4 }
                                        color: "#00d4ff"
                                        font { pixelSize: 9; family: "Consolas" }
                                        verticalAlignment: Text.AlignVCenter
                                        onTextChanged: manualLocationChanged()
                                    }
                                }
                            }
                        }

                        // Show avatar toggle
                        RowLayout {
                            spacing: 8
                            Layout.fillWidth: true
                            Text { text: "😺"; font.pixelSize: 10 }
                            Text { text: "Show Avatar"; color: Qt.rgba(0, 1, 1, 0.4); font { pixelSize: 8; family: "Consolas" } }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                id: avatarToggleBtn
                                width: 36; height: 18; radius: 9
                                color: root.showAvatar ? "#00ff88" : "#333"
                                border.color: Qt.rgba(0, 1, 1, 0.15); border.width: 1

                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        root.showAvatar = !root.showAvatar
                                        var settings = JSON.parse(bridge.getSettings())
                                        settings.avatar = settings.avatar || {}
                                        settings.avatar.enabled = root.showAvatar
                                        bridge.saveSettings(JSON.stringify(settings))
                                    }
                                }
                                Rectangle {
                                    x: root.showAvatar ? 19 : 1
                                    width: 16; height: 16; radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }

                        // Auto-start on boot toggle
                        RowLayout {
                            spacing: 8
                            Layout.fillWidth: true
                            Text { text: "🚀"; font.pixelSize: 10 }
                            Text { text: "Start on boot"; color: Qt.rgba(0, 1, 1, 0.4); font { pixelSize: 8; family: "Consolas" } }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                id: startupToggle
                                width: 36; height: 18; radius: 9
                                property bool isStartupActive: false
                                color: isStartupActive ? "#00ff88" : "#333"
                                border.color: Qt.rgba(0, 1, 1, 0.15); border.width: 1
                                Component.onCompleted: isStartupActive = bridge.isStartupEnabled()

                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        startupToggle.isStartupActive = !startupToggle.isStartupActive
                                        bridge.toggleStartup()
                                    }
                                }
                                Rectangle {
                                    x: startupToggle.isStartupActive ? 19 : 1
                                    width: 16; height: 16; radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }

                        // Create Desktop Shortcut button
                        Rectangle {
                            Layout.fillWidth: true; height: 24; radius: 4
                            color: shortcutMa.containsMouse ? Qt.rgba(0, 1, 1, 0.2) : Qt.rgba(0, 1, 1, 0.06)
                            border.color: Qt.rgba(0, 1, 1, 0.2); border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "🖥️ Create Desktop Shortcut"
                                color: Qt.rgba(0, 1, 1, 0.6)
                                font { pixelSize: 8; family: "Consolas"; bold: true }
                            }
                            MouseArea {
                                id: shortcutMa
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (bridge.createDesktopShortcut()) {
                                        bridge.playSound("click")
                                    }
                                }
                            }
                        }

                        // Hologram Theme Selector
                        RowLayout {
                            spacing: 8
                            Layout.fillWidth: true
                            Text { text: "🎨"; font.pixelSize: 10 }
                            Text { text: "Hologram Theme"; color: Qt.rgba(0, 1, 1, 0.4); font { pixelSize: 8; family: "Consolas" } }
                            Item { Layout.fillWidth: true }
                            
                            RowLayout {
                                spacing: 4
                                
                                Rectangle {
                                    width: 12; height: 12; radius: 6
                                    color: "#00F5FF"
                                    border.color: root.themeName === "cyan" ? "white" : "transparent"
                                    border.width: 1
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            root.changeTheme("cyan")
                                            bridge.playSound("click")
                                            var settings = JSON.parse(bridge.getSettings())
                                            settings.avatar = settings.avatar || {}
                                            settings.avatar.theme = "cyan"
                                            bridge.saveSettings(JSON.stringify(settings))
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 12; height: 12; radius: 6
                                    color: "#FFD700"
                                    border.color: (root.themeName === "gold" || root.themeName === "jarvis") ? "white" : "transparent"
                                    border.width: 1
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            root.changeTheme("gold")
                                            bridge.playSound("click")
                                            var settings = JSON.parse(bridge.getSettings())
                                            settings.avatar = settings.avatar || {}
                                            settings.avatar.theme = "gold"
                                            bridge.saveSettings(JSON.stringify(settings))
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 12; height: 12; radius: 6
                                    color: "#FF3344"
                                    border.color: (root.themeName === "crimson" || root.themeName === "red") ? "white" : "transparent"
                                    border.width: 1
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            root.changeTheme("crimson")
                                            bridge.playSound("click")
                                            var settings = JSON.parse(bridge.getSettings())
                                            settings.avatar = settings.avatar || {}
                                            settings.avatar.theme = "crimson"
                                            bridge.saveSettings(JSON.stringify(settings))
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 12; height: 12; radius: 6
                                    color: "#00FF66"
                                    border.color: (root.themeName === "green" || root.themeName === "matrix") ? "white" : "transparent"
                                    border.width: 1
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            root.changeTheme("green")
                                            bridge.playSound("click")
                                            var settings = JSON.parse(bridge.getSettings())
                                            settings.avatar = settings.avatar || {}
                                            settings.avatar.theme = "green"
                                            bridge.saveSettings(JSON.stringify(settings))
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 12; height: 12; radius: 6
                                    color: "#D000FF"
                                    border.color: (root.themeName === "purple" || root.themeName === "hermas") ? "white" : "transparent"
                                    border.width: 1
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            root.changeTheme("purple")
                                            bridge.playSound("click")
                                            var settings = JSON.parse(bridge.getSettings())
                                            settings.avatar = settings.avatar || {}
                                            settings.avatar.theme = "purple"
                                            bridge.saveSettings(JSON.stringify(settings))
                                        }
                                    }
                                }
                            }
                        }

                        // Connect with Phone button
                        Rectangle {
                            Layout.fillWidth: true; height: 24; radius: 4
                            color: phoneBridgeMa.containsMouse ? Qt.rgba(0, 1, 1, 0.2) : Qt.rgba(0, 1, 1, 0.06)
                            border.color: Qt.rgba(0, 1, 1, 0.2); border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "📱 Connect with Phone"
                                color: Qt.rgba(0, 1, 1, 0.6)
                                font { pixelSize: 8; family: "Consolas"; bold: true }
                            }
                            MouseArea {
                                id: phoneBridgeMa
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    var res = JSON.parse(bridge.startPhoneBridge())
                                    if (res.ok) {
                                        phoneBridgeUrl = res.url
                                        phoneBridgePin = res.pin
                                        phoneBridgeQr = res.qr_path + "?t=" + Date.now()
                                        phoneBridgeWindowShown = true
                                        registerHotspots()
                                        hotspotTimer.start()
                                    }
                                }
                            }
                        }

                        // Stop IRA button
                        Rectangle {
                            Layout.fillWidth: true; height: 24; radius: 4
                            color: stopIrMa.containsMouse ? Qt.rgba(1, 0.27, 0.27, 0.2) : Qt.rgba(1, 0.27, 0.27, 0.06)
                            border.color: Qt.rgba(1, 0.27, 0.27, 0.2); border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "⏹ Stop IRA"
                                color: Qt.rgba(1, 0.27, 0.27, 0.6)
                                font { pixelSize: 8; family: "Consolas"; bold: true }
                            }
                            MouseArea { id: stopIrMa; anchors.fill: parent; hoverEnabled: true; onClicked: bridge.stopIRA() }
                        }

                        // About IRA button
                        Rectangle {
                            Layout.fillWidth: true; height: 24; radius: 4
                            color: aboutIrMa.containsMouse ? Qt.rgba(0, 1, 0.5, 0.2) : Qt.rgba(0, 1, 0.5, 0.06)
                            border.color: Qt.rgba(0, 1, 0.5, 0.2); border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "ℹ About IRA"
                                color: Qt.rgba(0, 1, 0.5, 0.6)
                                font { pixelSize: 8; family: "Consolas"; bold: true }
                            }
                            MouseArea {
                                id: aboutIrMa
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    bridge.showAboutNodes()
                                    rightPanelShown = false
                                }
                            }
                        }
                    }

                }

                Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(0, 1, 1, 0.06) }

                // ── MENU ──
                Text {
                    text: "MENU"
                    color: Qt.rgba(0, 1, 1, 0.3)
                    font { pixelSize: 7; family: "Consolas"; bold: true; letterSpacing: 2 }
                }

                Repeater {
                    model: ListModel {
                        ListElement { label: "All Tools"; icon: "⚡" }
                        ListElement { label: "Memory"; icon: "🧠" }
                        ListElement { label: "Todo"; icon: "📋" }
                        ListElement { label: "Nodes"; icon: "🎛" }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 30
                        radius: 6
                        color: menuItemMa.containsMouse ? Qt.rgba(0, 1, 1, 0.08) :
                               ((model.label === "Todo" && todoSectionVisible) ||
                                (model.label === "Nodes" && showNodes) ? Qt.rgba(0, 1, 1, 0.05) : "transparent")
                        border.color: menuItemMa.containsMouse ? Qt.rgba(0, 1, 1, 0.12) : "transparent"
                        border.width: 1

                        RowLayout {
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            spacing: 8
                            Text { text: model.icon; font.pixelSize: 13 }
                            Text {
                                text: model.label
                                color: Qt.rgba(0, 1, 1, 0.55)
                                font { pixelSize: 10; family: "Consolas" }
                                Layout.fillWidth: true
                            }
                            Text {
                                text: model.label === "Todo" ? (todoSectionVisible ? "▾" : "▸") :
                                      (model.label === "Nodes" ? (showNodes ? "●" : "○") : "▸")
                                color: Qt.rgba(0, 1, 1, 0.2); font.pixelSize: 9
                            }
                        }
                        MouseArea {
                            id: menuItemMa; anchors.fill: parent; hoverEnabled: true
                            onClicked: {
                                if (model.label === "All Tools") { toolWindowShown = true; registerHotspots(); hotspotTimer.start() }
                                else if (model.label === "Memory") { memoryWindowShown = true; bridge.listMemory(); registerHotspots(); hotspotTimer.start() }
                                else if (model.label === "Todo") { todoSectionVisible = !todoSectionVisible; bridge.refreshTodo(); registerHotspots(); hotspotTimer.start() }
                                else if (model.label === "Nodes") { showNodes = !showNodes; registerHotspots(); hotspotTimer.start() }
                            }
                        }
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                }



                // ── TODO SECTION ──
                Rectangle {
                    id: todoSection
                    Layout.fillWidth: true
                    Layout.preferredHeight: todoSectionVisible ? todoInner.implicitHeight + 12 : 0
                    clip: true
                    color: "transparent"
                    visible: todoSectionVisible

                    Behavior on Layout.preferredHeight { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }

                    ColumnLayout {
                        id: todoInner
                        width: parent.width
                        spacing: 4
                        anchors { top: parent.top; left: parent.left; right: parent.right; topMargin: 4 }

                        Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(0, 1, 1, 0.06) }

                        Repeater {
                            model: todoModel
                            Rectangle {
                                width: todoInner.width; height: 28; radius: 5
                                color: Qt.rgba(0, 1, 1, 0.03)
                                border.color: Qt.rgba(0, 1, 1, 0.06); border.width: 1

                                RowLayout {
                                    anchors { fill: parent; leftMargin: 6; rightMargin: 4 }
                                    spacing: 5

                                    Rectangle {
                                        width: 12; height: 12; radius: 6
                                        color: model.completed ? Qt.rgba(0, 1, 0.5, 0.3) : "transparent"
                                        border.color: model.completed ? "#00FF88" : Qt.rgba(0, 1, 1, 0.3); border.width: 1
                                        Text { anchors.centerIn: parent; text: model.completed ? "✓" : ""; color: "#00FF88"; font.pixelSize: 7; font.bold: true }
                                        MouseArea { anchors.fill: parent; onClicked: bridge.todoComplete(model.id) }
                                    }

                                    Text {
                                        text: model.task || model.text || ""
                                        color: model.completed ? Qt.rgba(0, 1, 1, 0.25) : Qt.rgba(0, 1, 1, 0.65)
                                        font { pixelSize: 9; family: "Consolas"; strikeout: model.completed }
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight; maximumLineCount: 1
                                    }

                                    Rectangle {
                                        width: 13; height: 13; radius: 6
                                        color: todoDelMa.containsMouse ? Qt.rgba(1, 0.2, 0.2, 0.3) : "transparent"
                                        Text { anchors.centerIn: parent; text: "✕"; color: Qt.rgba(1, 0.3, 0.3, 0.5); font.pixelSize: 7 }
                                        MouseArea { id: todoDelMa; anchors.fill: parent; hoverEnabled: true; onClicked: bridge.todoRemove(model.id) }
                                    }
                                }
                            }
                        }

                        Text {
                            visible: todoModel.count === 0
                            Layout.alignment: Qt.AlignHCenter
                            text: "No todos"
                            color: Qt.rgba(0, 1, 1, 0.2)
                            font { pixelSize: 8; family: "Consolas" }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 24; radius: 5
                            color: Qt.rgba(0, 0, 0, 0.2)
                            border.color: todoInput.activeFocus ? Qt.rgba(0, 1, 1, 0.25) : Qt.rgba(0, 1, 1, 0.08)
                            border.width: 1

                            TextField {
                                id: todoInput
                                anchors { fill: parent; leftMargin: 6; rightMargin: 6 }
                                placeholderText: "+ Add todo…"
                                placeholderTextColor: Qt.rgba(0, 1, 1, 0.15)
                                color: "#B0D0E0"
                                font { pixelSize: 9; family: "Consolas" }
                                background: Item {}
                                onAccepted: {
                                    if (text.trim().length > 0) {
                                        bridge.todoAdd(text.trim())
                                        text = ""
                                    }
                                }
                            }
                        }
                    }
                }

                Item { Layout.preferredHeight: 10 }
            }
        }
    }

    // Right edge handle
    Rectangle {
        id: rightEdgeHandle
        x: root.width - 7; y: root.height / 2 - 35
        width: 7; height: 70
        color: rightEdgeMa.containsMouse ? Qt.rgba(0, 0.5, 1, 0.18) : Qt.rgba(0, 0.024, 0.059, 0.45)
        visible: !rightPanelShown; z: 5
        opacity: isBooting ? 0 : 1.0

        Rectangle {
            anchors { left: parent.left; verticalCenter: parent.verticalCenter }
            width: 2; height: 22; radius: 1
            color: Qt.rgba(0, 0.5, 1, 0.3)

            // Pulse animation
            SequentialAnimation on height {
                running: !rightPanelShown && !isBooting; loops: Animation.Infinite
                NumberAnimation { from: 18; to: 28; duration: 1200; easing.type: Easing.InOutSine }
                NumberAnimation { from: 28; to: 18; duration: 1200; easing.type: Easing.InOutSine }
            }
        }
        MouseArea {
            id: rightEdgeMa; anchors.fill: parent; hoverEnabled: true
            onClicked: { activateWindow(); rightPanelShown = true; registerHotspots(); hotspotTimer.start() }
        }

        Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
    }

    // ═══════════════════════════════════════════════
    //  CHAT POPUP — Compact, above dock
    // ═══════════════════════════════════════════════
    Rectangle {
        id: chatPopup
        x: root.width / 2 - chatW / 2
        y: chatPopupShown && dockExpanded
            ? (root.height - dockH - bottomMargin - chatH - 8)
            : (root.height - dockH - bottomMargin)
        width: chatW
        height: chatPopupShown ? chatH : 0
        radius: 18
        color: Qt.rgba(0, 0.03, 0.07, 0.88)
        border.color: Qt.rgba(0, 1, 1, 0.22); border.width: 1.5
        clip: true
        visible: chatPopupShown && dockExpanded && height > 0
        z: 18

        Behavior on y { NumberAnimation { duration: 280; easing.type: Easing.OutQuad } }
        Behavior on height { NumberAnimation { duration: 280; easing.type: Easing.OutQuad } }



        // Processing glow border
        Rectangle {
            anchors.fill: parent; anchors.margins: -1
            radius: 15; color: "transparent"
            border.color: stateColor; border.width: 2
            visible: isProcessing
            SequentialAnimation on opacity {
                running: isProcessing; loops: Animation.Infinite
                NumberAnimation { from: 0.15; to: 0.55; duration: 800; easing.type: Easing.InOutSine }
                NumberAnimation { from: 0.55; to: 0.15; duration: 800; easing.type: Easing.InOutSine }
            }
        }

        // Status bar
        Rectangle {
            id: chatStatusBar
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 22; color: Qt.rgba(0, 0, 0, 0.3); z: 2

            Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 14; height: 14; color: parent.color }
            Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 14; height: 14; color: parent.color }

            RowLayout {
                anchors { fill: parent; leftMargin: 10; rightMargin: 8 }
                spacing: 5
                Rectangle { width: 5; height: 5; radius: 3; color: stateColor }
                Text { text: (currentExpression !== "normal" ? ("[" + currentExpression.toUpperCase() + "] ") : "") + (isProcessing ? processingStatusText : stateText); color: Qt.rgba(0, 1, 1, 0.45); font { pixelSize: 9; family: "Consolas" } }
                Item { Layout.fillWidth: true }

                // Expand / collapse chat
                Rectangle {
                    width: 16; height: 16; radius: 3
                    color: expandChatMa.containsMouse ? Qt.rgba(0, 1, 1, 0.1) : "transparent"
                    Text { anchors.centerIn: parent; text: chatExpanded ? "▼" : "▲"; color: Qt.rgba(0, 1, 1, 0.35); font.pixelSize: 7 }
                    MouseArea { id: expandChatMa; anchors.fill: parent; hoverEnabled: true; onClicked: { chatExpanded = !chatExpanded; registerHotspots(); hotspotTimer.start() } }
                }
                // Close chat
                Rectangle {
                    width: 16; height: 16; radius: 3
                    color: closeChatMa.containsMouse ? Qt.rgba(1, 0.27, 0.27, 0.15) : "transparent"
                    Text { anchors.centerIn: parent; text: "✕"; color: Qt.rgba(1, 0.27, 0.27, 0.45); font.pixelSize: 8 }
                    MouseArea { id: closeChatMa; anchors.fill: parent; hoverEnabled: true; onClicked: { chatPopupShown = false; registerHotspots(); hotspotTimer.start() } }
                }
            }
        }

        // Chat content - WhatsApp Style
        ListView {
            id: chatListView
            anchors { top: chatStatusBar.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 16 }
            model: chatModel
            clip: true
            spacing: 14
            boundsBehavior: Flickable.StopAtBounds
            footer: Item {
                width: chatListView.width
                height: 120
            }

            property bool userAtBottom: true
            property bool _programmaticScroll: false

            function isAtBottom(): bool {
                return (contentHeight <= height) || (contentY + height >= contentHeight - 40)
            }

            function smartScroll() {
                if (userAtBottom) {
                    _programmaticScroll = true
                    positionViewAtEnd()
                    _programmaticScroll = false
                }
            }

            function forceScrollToBottom() {
                userAtBottom = true
                _programmaticScroll = true
                positionViewAtEnd()
                _programmaticScroll = false
            }

            onContentYChanged: {
                if (!_programmaticScroll) {
                    userAtBottom = isAtBottom()
                }
            }

            ScrollBar.vertical: ScrollBar {
                id: chatScroll
                policy: ScrollBar.AsNeeded
                active: chatListView.activeFocus || chatScroll.hovered || chatScroll.active
                contentItem: Rectangle {
                    implicitWidth: 4
                    radius: 2
                    color: chatScroll.pressed ? "#00FFFF" : Qt.rgba(0, 1, 1, 0.25)
                }
            }

            delegate: Item {
                id: delegateItem
                width: chatListView.width
                height: (isThinking ? thinkBubble.height : (isTool ? toolBubble.height : bubble.height)) + 4

                readonly property bool isUser: model.sender === "user"
                readonly property bool isThinking: model.sender === "thinking"
                readonly property bool isTool: model.sender === "tool"
                property bool collapsed: false

                Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.InOutQuad } }

                opacity: 0
                transform: Translate { id: trans; y: 20 }

                Component.onCompleted: {
                    fadeInAnim.start()
                }

                ParallelAnimation {
                    id: fadeInAnim
                    NumberAnimation { target: delegateItem; property: "opacity"; to: 1.0; duration: 350; easing.type: Easing.OutCubic }
                    NumberAnimation { target: trans; property: "y"; to: 0; duration: 350; easing.type: Easing.OutCubic }
                }

                // ═══ THINKING BUBBLE ═══
                Rectangle {
                    id: thinkBubble
                    visible: isThinking
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    width: Math.min(chatListView.width * 0.85, Math.max(200, thinkContent.implicitWidth + 24))
                    height: thinkContent.implicitHeight + 16
                    radius: 10
                    color: Qt.rgba(0.06, 0.04, 0.0, 0.6)
                    border.color: Qt.rgba(1, 0.7, 0, 0.25)
                    border.width: 1

                    ColumnLayout {
                        id: thinkContent
                        anchors { fill: parent; margins: 10 }
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle {
                                width: 16; height: 16; radius: 4
                                color: Qt.rgba(1, 0.7, 0, 0.15)
                                Text { anchors.centerIn: parent; text: "🤔"; font.pixelSize: 10 }
                            }
                            Text {
                                text: "REASONING"
                                color: "#FFAA00"
                                font { pixelSize: 8; family: "Consolas"; bold: true; letterSpacing: 1.5 }
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: collapsed ? "▶" : "▼"
                                color: Qt.rgba(1, 0.7, 0, 0.4)
                                font { pixelSize: 8 }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: !collapsed
                            text: model.text
                            color: "#E0C080"
                            font { pixelSize: 10; family: "Consolas" }
                            wrapMode: Text.WordWrap
                            maximumLineCount: 12
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            collapsed = !collapsed
                            bridge.playSound(collapsed ? "collapse" : "expand")
                        }
                    }

                    Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.InOutQuad } }
                }

                // ═══ TOOL CALL BUBBLE ═══
                Rectangle {
                    id: toolBubble
                    visible: isTool
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    width: Math.min(chatListView.width * 0.85, Math.max(220, toolContent.implicitWidth + 24))
                    height: toolContent.implicitHeight + 16
                    radius: 10
                    color: Qt.rgba(0, 0.06, 0.08, 0.6)
                    border.color: Qt.rgba(0, 1, 1, 0.25)
                    border.width: 1

                    ColumnLayout {
                        id: toolContent
                        anchors { fill: parent; margins: 10 }
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle {
                                width: 16; height: 16; radius: 4
                                color: Qt.rgba(0, 1, 1, 0.15)
                                Text { anchors.centerIn: parent; text: "🔧"; font.pixelSize: 10 }
                            }
                            Text {
                                text: model.toolName
                                color: "#00FFFF"
                                font { pixelSize: 10; family: "Consolas"; bold: true }
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: collapsed ? "▶" : "▼"
                                color: Qt.rgba(0, 1, 1, 0.4)
                                font { pixelSize: 8 }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: !collapsed && model.toolArgs !== ""
                            text: model.toolArgs
                            color: "#80CCCC"
                            font { pixelSize: 9; family: "Consolas" }
                            wrapMode: Text.WordWrap
                            maximumLineCount: 8
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }

                        // Tool result (when available)
                        Rectangle {
                            Layout.fillWidth: true
                            visible: !collapsed && model.toolResult !== ""
                            height: toolResultText.implicitHeight + 12
                            radius: 6
                            color: Qt.rgba(0, 0.12, 0.08, 0.4)
                            border.color: Qt.rgba(0, 0.8, 0.4, 0.15)
                            border.width: 1

                            Text {
                                id: toolResultText
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 6 }
                                text: "→ " + model.toolResult
                                color: "#80DDAA"
                                font { pixelSize: 9; family: "Consolas" }
                                wrapMode: Text.WordWrap
                                maximumLineCount: 6
                                elide: Text.ElideRight
                                textFormat: Text.PlainText
                            }
                        }

                        // Loading indicator when no result yet
                        RowLayout {
                            visible: !collapsed && model.toolResult === ""
                            spacing: 4
                            Rectangle {
                                width: 4; height: 4; radius: 2; color: "#00FFFF"
                                SequentialAnimation on opacity {
                                    running: true; loops: Animation.Infinite
                                    NumberAnimation { from: 0.3; to: 1.0; duration: 400 }
                                    NumberAnimation { from: 1.0; to: 0.3; duration: 400 }
                                }
                            }
                            Text {
                                text: "executing..."
                                color: Qt.rgba(0, 1, 1, 0.5)
                                font { pixelSize: 8; family: "Consolas"; italic: true }
                            }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            collapsed = !collapsed
                            bridge.playSound(collapsed ? "collapse" : "expand")
                        }
                    }

                    Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.InOutQuad } }
                }

                // ═══ USER / IRA BUBBLE (original) ═══
                Rectangle {
                    id: bubble
                    visible: !isThinking && !isTool

                    property string msgImagePath: (model && model.imagePath !== undefined) ? model.imagePath : ""
                    property string msgLargeText: (model && model.largeText !== undefined) ? model.largeText : ""
                    property string msgText: (model && model.text !== undefined) ? model.text : ""
                    property bool msgIsThinking: (model && model.isThinking !== undefined) ? model.isThinking : false
                    property string msgToolLogs: (model && model.toolLogs !== undefined) ? model.toolLogs : ""

                    anchors.right: isUser ? parent.right : undefined
                    anchors.rightMargin: isUser ? 8 : 0
                    anchors.left: !isUser ? parent.left : undefined
                    anchors.leftMargin: !isUser ? 8 : 0
                    
                    width: isUser 
                        ? Math.min(chatListView.width * 0.78, Math.max(140, bubbleLayout.implicitWidth + 24))
                        : chatListView.width - 16
                    
                    height: bubbleLayout.implicitHeight + 16
                    radius: 12
                    Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.InOutQuad } }
                    
                    color: isUser ? Qt.rgba(0, 0.18, 0.28, 0.72) : "transparent"
                    border.color: isUser ? Qt.rgba(0, 1, 1, 0.25) : "transparent"
                    border.width: isUser ? 1 : 0

                    ColumnLayout {
                        id: bubbleLayout
                        anchors { fill: parent; margins: 10 }
                        spacing: 6

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                text: isUser ? "YOU" : "IRA"
                                color: isUser ? "#00FFFF" : "#0080FF"
                                font { pixelSize: 9; family: "Consolas"; bold: true; letterSpacing: 1.5 }
                            }
                            Item { Layout.fillWidth: true }
                            
                            Text {
                                visible: isUser && bubble.msgImagePath !== "" && bubble.msgImagePath !== "[]"
                                text: "🖼 Image Attached"
                                color: Qt.rgba(0, 1, 1, 0.6)
                                font { pixelSize: 8; family: "Consolas" }
                            }
                            
                            Text {
                                visible: isUser && bubble.msgLargeText !== "" && bubble.msgLargeText !== "[]"
                                text: "📄 Text Attached"
                                color: Qt.rgba(0, 1, 1, 0.6)
                                font { pixelSize: 8; family: "Consolas" }
                            }
                            
                            Rectangle {
                                width: 20; height: 20; radius: 4
                                color: copyBtnMa.containsMouse ? Qt.rgba(0, 1, 1, 0.15) : "transparent"
                                border.color: copyBtnMa.containsMouse ? Qt.rgba(0, 1, 1, 0.3) : Qt.rgba(0, 1, 1, 0.1)
                                border.width: 1
                                Text {
                                    anchors.centerIn: parent
                                    text: "📋"
                                    font.pixelSize: 10
                                    color: copyBtnMa.containsMouse ? "#00FFFF" : Qt.rgba(0, 1, 1, 0.5)
                                }
                                MouseArea {
                                    id: copyBtnMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        bridge.copyToClipboard(bubble.msgText)
                                        bridge.playSound("click")
                                    }
                                }
                                Behavior on color { ColorAnimation { duration: 100 } }
                            }
                        }

                        // Attached Images
                        Repeater {
                            model: getImageList(bubble.msgImagePath)
                            delegate: Image {
                                visible: modelData !== ""
                                source: modelData ? (modelData.indexOf("file://") === 0 ? modelData : "file:///" + modelData) : ""
                                Layout.preferredWidth: 280
                                Layout.preferredHeight: 180
                                fillMode: Image.PreserveAspectFit
                                Layout.alignment: Qt.AlignLeft

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: Qt.openUrlExternally(parent.source)
                                }
                            }
                        }

                        // Attached Texts
                        Repeater {
                            model: getTextList(bubble.msgLargeText)
                            delegate: Rectangle {
                                visible: modelData !== ""
                                Layout.preferredWidth: Math.min(280, bubbleLayout.width - 24)
                                Layout.preferredHeight: Math.min(80, textPreviewLabel.implicitHeight + 16)
                                radius: 6
                                color: Qt.rgba(0, 0.1, 0.15, 0.5)
                                border.color: Qt.rgba(0, 1, 1, 0.2)
                                border.width: 1

                                Text {
                                    id: textPreviewLabel
                                    anchors { fill: parent; margins: 8 }
                                    text: modelData
                                    color: "#E0FFFF"
                                    font { pixelSize: 10; family: "Consolas" }
                                    wrapMode: Text.WordWrap
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            visible: !isUser
                            implicitHeight: streamingCursor.visible ? 4 : 0
                            Text {
                                id: streamingCursor
                                visible: !isUser && bubble.msgIsThinking && bubble.msgText !== ""
                                text: "▌"
                                color: "#00d4ff"
                                font { pixelSize: 11; family: "Consolas"; bold: true }
                                SequentialAnimation on opacity {
                                    running: streamingCursor.visible
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 0.95; to: 0.1; duration: 480; easing.type: Easing.InOutQuad }
                                    NumberAnimation { from: 0.1; to: 0.95; duration: 480; easing.type: Easing.InOutQuad }
                                }
                            }
                        }

                        Text {
                            id: messageText
                            text: bubble.msgText
                            color: isUser ? "#E0F7FA" : "#B0D0E0"
                            font { pixelSize: 11; family: "Consolas" }
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                            textFormat: Text.RichText
                        }

                        // Legacy toolLogs (for backward compat)
                        ColumnLayout {
                            visible: !isUser && bubble.msgToolLogs !== ""
                            Layout.fillWidth: true
                            spacing: 0

                            Rectangle {
                                Layout.fillWidth: true
                                height: 22; radius: 6
                                color: toolHeaderMa.containsMouse ? Qt.rgba(0, 1, 1, 0.08) : Qt.rgba(0, 0.08, 0.15, 0.5)
                                border.color: Qt.rgba(0, 1, 1, 0.12); border.width: 1

                                RowLayout {
                                    anchors { fill: parent; leftMargin: 8; rightMargin: 6 }
                                    spacing: 5
                                    Rectangle {
                                        width: 14; height: 14; radius: 3
                                        color: Qt.rgba(0, 1, 1, 0.12)
                                        Text { anchors.centerIn: parent; text: "⚙"; font.pixelSize: 8; color: Qt.rgba(0, 1, 1, 0.6) }
                                    }
                                    Text {
                                        text: "TOOLS"
                                        color: Qt.rgba(0, 1, 1, 0.5)
                                        font { pixelSize: 8; family: "Consolas"; bold: true; letterSpacing: 1.5 }
                                    }
                                    Item { Layout.fillWidth: true }
                                    Text {
                                        text: collapsed ? "▶" : "▼"
                                        color: Qt.rgba(0, 1, 1, 0.3)
                                        font { pixelSize: 7; family: "Consolas" }
                                    }
                                }
                                MouseArea {
                                    id: toolHeaderMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        collapsed = !collapsed
                                        bridge.playSound(collapsed ? "collapse" : "expand")
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: collapsed ? 0 : logContent2.implicitHeight + 16
                                clip: true
                                visible: height > 0
                                color: Qt.rgba(0, 0.04, 0.08, 0.4)

                                Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.InOutQuad } }

                                Text {
                                    id: logContent2
                                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 8 }
                                    text: bubble.msgToolLogs
                                    color: "#00CCBB"
                                    font { pixelSize: 9; family: "Consolas" }
                                    wrapMode: Text.WordWrap
                                    textFormat: Text.PlainText
                                    maximumLineCount: 20
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        // Thinking indicator (IRA thinking, no text yet)
                        RowLayout {
                            visible: !isUser && bubble.msgIsThinking && bubble.msgText === "" && bubble.msgToolLogs === ""
                            spacing: 6
                            Rectangle {
                                width: 4; height: 14; radius: 2
                                color: "#00FFFF"
                                SequentialAnimation on opacity {
                                    running: visible
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 0.3; to: 1.0; duration: 550; easing.type: Easing.InOutQuad }
                                    NumberAnimation { from: 1.0; to: 0.3; duration: 550; easing.type: Easing.InOutQuad }
                                }
                            }
                            Text {
                                text: isProcessing ? processingStatusText : (phaseLabel || stateText || "Thinking")
                                color: Qt.rgba(0, 1, 1, 0.7)
                                font { pixelSize: 10; family: "Consolas" }
                            }
                            RowLayout {
                                spacing: 4
                                Rectangle { width: 5; height: 5; radius: 3; color: "#00FFFF"
                                    SequentialAnimation on opacity { running: true; loops: Animation.Infinite
                                        NumberAnimation { from: 0.15; to: 1.0; duration: 450 }
                                        NumberAnimation { from: 1.0; to: 0.15; duration: 450 }
                                    }
                                }
                                Rectangle { width: 5; height: 5; radius: 3; color: "#00FFFF"
                                    SequentialAnimation on opacity { running: true; loops: Animation.Infinite
                                        PauseAnimation { duration: 200 }
                                        NumberAnimation { from: 0.15; to: 1.0; duration: 450 }
                                        NumberAnimation { from: 1.0; to: 0.15; duration: 450 }
                                    }
                                }
                                Rectangle { width: 5; height: 5; radius: 3; color: "#00FFFF"
                                    SequentialAnimation on opacity { running: true; loops: Animation.Infinite
                                        PauseAnimation { duration: 400 }
                                        NumberAnimation { from: 0.15; to: 1.0; duration: 450 }
                                        NumberAnimation { from: 1.0; to: 0.15; duration: 450 }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            onContentHeightChanged: {
                chatListView.smartScroll()
            }

            // Scroll to bottom button
            Rectangle {
                anchors { bottom: parent.bottom; right: parent.right; bottomMargin: 8; rightMargin: 8 }
                width: 28; height: 28; radius: 14
                visible: !chatListView.userAtBottom
                color: scrollDownBtnMa.containsMouse ? Qt.rgba(0, 1, 1, 0.25) : Qt.rgba(0, 0.15, 0.25, 0.8)
                border.color: Qt.rgba(0, 1, 1, 0.35); border.width: 1
                z: 5

                Text { anchors.centerIn: parent; text: "⬇"; color: "#00FFFF"; font.pixelSize: 12 }

                MouseArea {
                    id: scrollDownBtnMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        chatListView.forceScrollToBottom()
                    }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════
    //  BOTTOM DOCK — Floating feel (pushed up)
    // ═══════════════════════════════════════════════

    // Dock glow when processing
    Rectangle {
        anchors.fill: dock; anchors.margins: -2
        radius: 20; color: "transparent"
        border.color: stateColor; border.width: 2
        visible: isProcessing && dockExpanded
        SequentialAnimation on opacity {
            running: isProcessing; loops: Animation.Infinite
            NumberAnimation { from: 0.1; to: 0.55; duration: 900; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.55; to: 0.1; duration: 900; easing.type: Easing.InOutSine }
        }
    }

    // Attachment Preview Card — multi-item chips
    Rectangle {
        id: attachmentPreviewCard
        anchors.bottom: dock.top
        anchors.bottomMargin: 8
        anchors.horizontalCenter: dock.horizontalCenter
        width: dock.width
        height: (attachedImagesModel.count + attachedTextsModel.count > 0) ? chipFlow.implicitHeight + 16 : 0
        radius: 14
        color: Qt.rgba(0, 0.024, 0.059, 0.86)
        border.color: Qt.rgba(0, 1, 1, 0.22)
        border.width: 1.5
        visible: (attachedImagesModel.count + attachedTextsModel.count > 0) && dockExpanded
        z: 19

        Flickable {
            id: chipRow
            anchors.fill: parent
            anchors.margins: 6
            contentWidth: chipFlow.implicitWidth
            contentHeight: chipFlow.implicitHeight
            clip: true
            flickableDirection: Flickable.HorizontalFlick

            Flow {
                id: chipFlow
                spacing: 6
                width: parent.width

                // Image chips
                Repeater {
                    model: attachedImagesModel
                    Rectangle {
                        width: 42; height: 42; radius: 8
                        color: Qt.rgba(0, 0.15, 0.2, 0.7)
                        border.color: Qt.rgba(0, 1, 1, 0.3); border.width: 1

                        Image {
                            anchors.fill: parent; anchors.margins: 2
                            source: model.path
                            fillMode: Image.PreserveAspectCrop
                        }
                        Rectangle {
                            anchors.top: parent.top; anchors.right: parent.right; anchors.margins: -3
                            width: 12; height: 12; radius: 6
                            color: "#FF4444"
                            Text { anchors.centerIn: parent; text: "✕"; color: "white"; font.pixelSize: 7; font.bold: true }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    attachedImagesModel.remove(index)
                                    if (attachedImagesModel.count === 0) attachedImage = ""
                                    registerHotspots(); hotspotTimer.start()
                                }
                            }
                        }
                    }
                }

                // Text chips
                Repeater {
                    model: attachedTextsModel
                    Rectangle {
                        width: Math.min(chipFlow.width, Math.max(100, textChipLabel.implicitWidth + 30)); height: 28; radius: 8
                        color: Qt.rgba(0.05, 0.05, 0.15, 0.7)
                        border.color: Qt.rgba(0, 1, 1, 0.2); border.width: 1

                        Row {
                            anchors.centerIn: parent; spacing: 4
                            Text { text: "📄"; font.pixelSize: 10 }
                            Text {
                                id: textChipLabel
                                text: model.preview
                                color: "#B0D0E0"
                                font { pixelSize: 9; family: "Consolas" }
                                elide: Text.ElideRight
                                maximumLineCount: 1
                            }
                        }
                        Rectangle {
                            anchors.top: parent.top; anchors.right: parent.right; anchors.margins: -3
                            width: 12; height: 12; radius: 6
                            color: "#555555"
                            Text { anchors.centerIn: parent; text: "✕"; color: "white"; font.pixelSize: 7; font.bold: true }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    attachedTextsModel.remove(index)
                                    if (attachedTextsModel.count === 0) { attachedLargeText = ""; attachedLargeTextPreview = "" }
                                    registerHotspots(); hotspotTimer.start()
                                }
                            }
                        }
                    }
                }
            }
        }

        // Count badge
        Rectangle {
            anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 4
            width: countLabel.implicitWidth + 8; height: 14; radius: 7
            color: Qt.rgba(0, 1, 1, 0.2)
            visible: (attachedImagesModel.count + attachedTextsModel.count) > 1
            Text {
                id: countLabel
                anchors.centerIn: parent
                text: (attachedImagesModel.count + attachedTextsModel.count) + "/" + maxAttachments
                color: "#00FFFF"
                font { pixelSize: 7; family: "Consolas"; bold: true }
            }
        }

        onVisibleChanged: { registerHotspots(); hotspotTimer.start() }
    }

    // Voice glow above dock
    Rectangle {
        id: voiceGlow
        anchors.bottom: dock.top
        anchors.bottomMargin: (attachedImagesModel.count + attachedTextsModel.count > 0) ? 62 : 4
        anchors.horizontalCenter: dock.horizontalCenter
        width: dock.width - 24
        height: 18; radius: 9
        z: 15
        visible: isVoiceMode && dockExpanded

        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: voiceGlow.voiceGlowColor }
            GradientStop { position: 1.0; color: "transparent" }
        }

        readonly property string voiceGlowColor: {
            if (isProcessing) return "#FFAA00"
            else if (stateText === "Talking" || talkingTimer.running) return "#00FF88"
            else return "#00FFFF"
        }

        SequentialAnimation on opacity {
            running: voiceGlow.visible; loops: Animation.Infinite
            NumberAnimation { from: 0.3; to: 0.85; duration: 800; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 0.85; to: 0.3; duration: 800; easing.type: Easing.InOutQuad }
        }

        SequentialAnimation on height {
            running: voiceGlow.visible; loops: Animation.Infinite
            NumberAnimation { from: 10; to: 22; duration: 400; easing.type: Easing.InOutSine }
            NumberAnimation { from: 22; to: 10; duration: 400; easing.type: Easing.InOutSine }
        }
    }

    Rectangle {
        id: focusGlow
        anchors.bottom: dock.top
        anchors.bottomMargin: 4
        anchors.horizontalCenter: dock.horizontalCenter
        width: dock.width - 24
        height: 3
        radius: 1.5
        z: 15
        visible: inputField.activeFocus && root.active
        opacity: visible ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: "#00FFFF" }
            GradientStop { position: 1.0; color: "transparent" }
        }
        
        SequentialAnimation on opacity {
            running: focusGlow.visible; loops: Animation.Infinite
            NumberAnimation { from: 0.4; to: 1.0; duration: 600; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.0; to: 0.4; duration: 600; easing.type: Easing.InOutQuad }
        }
    }

    Rectangle {
        id: dock
        x: root.width / 2 - width / 2
        y: isBooting ? (root.height + 150) : (dockExpanded ? (root.height - dockH - bottomMargin) : (root.height + 10))
        width: chatW
        height: dockH; radius: 18
        color: (inputField.activeFocus && root.active) ? Qt.rgba(0, 0.04, 0.09, 0.94) : Qt.rgba(0, 0.024, 0.059, 0.82)
        border.color: (inputField.activeFocus && root.active) ? "#00FFFF" : Qt.rgba(0, 1, 1, 0.22)
        border.width: (inputField.activeFocus && root.active) ? 2.0 : 1.5
        visible: dockExpanded; z: 20
        opacity: isBooting ? 0 : 1.0
        scale: isBooting ? 0.8 : 1.0

        Behavior on y { NumberAnimation { duration: 850; easing.type: Easing.OutBack } }
        Behavior on color { ColorAnimation { duration: 200 } }
        Behavior on border.color { ColorAnimation { duration: 200 } }
        Behavior on border.width { NumberAnimation { duration: 200 } }
        Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
        Behavior on scale {
            NumberAnimation { duration: 1000; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.6 }
        }

        // Cinematic border glow on boot
        Rectangle {
            id: bootGlowRing
            anchors.fill: parent
            radius: 18
            color: "transparent"
            border.color: "#00FFFF"
            border.width: 1
            opacity: 0
            z: -1

            SequentialAnimation {
                id: dockGlowAnim
                running: false
                NumberAnimation { target: bootGlowRing; property: "opacity"; from: 0; to: 0.5; duration: 300 }
                NumberAnimation { target: bootGlowRing; property: "opacity"; from: 0.5; to: 0; duration: 800; easing.type: Easing.OutQuad }
            }
        }

        RowLayout {
            anchors { fill: parent; margins: 6; leftMargin: 12; rightMargin: 12 }
            spacing: 6

            // Logs/Gesture Sidebar Toggle
            Rectangle {
                id: logsBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : 1.0
                scale: isBooting ? 0.3 : 1.0
                color: logsDockMa.containsMouse ? Qt.rgba(0, 1, 0.5, 0.12) : Qt.rgba(0, 0, 0, 0.2)
                border.color: leftPanelShown ? Qt.rgba(0, 1, 0.5, 0.35) : Qt.rgba(0, 1, 0.5, 0.12); border.width: 1
                Text { anchors.centerIn: parent; text: "👁️"; font.pixelSize: 14 }
                MouseArea {
                    id: logsDockMa
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        activateWindow()
                        leftPanelShown = !leftPanelShown
                        registerHotspots()
                        hotspotTimer.start()
                        bridge.playSound(leftPanelShown ? "expand" : "collapse")
                    }
                }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttLogs
                    visible: logsDockMa.containsMouse
                    text: "Logs & Gestures"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttLogs.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }

            // Chat toggle (disabled during voice mode)
            Rectangle {
                id: chatBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : (isVoiceMode ? 0.3 : 1.0)
                scale: isBooting ? 0.3 : 1.0
                color: (isVoiceMode || chatDockMa.containsMouse) ? Qt.rgba(0, 1, 1, 0.12) : Qt.rgba(0, 0, 0, 0.2)
                border.color: chatPopupShown ? Qt.rgba(0, 1, 1, 0.4) : Qt.rgba(0, 1, 1, 0.18); border.width: 1
                Text { anchors.centerIn: parent; text: "💬"; font.pixelSize: 14 }
                MouseArea { id: chatDockMa; anchors.fill: parent; hoverEnabled: !isVoiceMode; onClicked: { if (!isVoiceMode) { activateWindow(); chatPopupShown = !chatPopupShown; registerHotspots(); hotspotTimer.start(); bridge.playSound(chatPopupShown ? "expand" : "collapse") } } }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttChat
                    visible: chatDockMa.containsMouse
                    text: "Toggle Chat Popup"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttChat.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }

            // Mic
            Rectangle {
                id: micBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : 1.0
                scale: isBooting ? 0.3 : 1.0
                color: isVoiceMode ? Qt.rgba(1, 0, 0, 0.28) : (micDockMa.containsMouse ? Qt.rgba(0, 1, 1, 0.1) : Qt.rgba(0, 0, 0, 0.2))
                border.color: isVoiceMode ? "#FF3333" : Qt.rgba(0, 1, 1, 0.18); border.width: 1
                Text {
                    anchors.centerIn: parent
                    text: "🎤"
                    color: isVoiceMode ? "#FF3333" : "#00FFFF"
                    font.pixelSize: 14
                    SequentialAnimation on opacity {
                        running: isVoiceMode; loops: Animation.Infinite
                        NumberAnimation { from: 0.4; to: 1.0; duration: 600 }
                        NumberAnimation { from: 1.0; to: 0.4; duration: 600 }
                    }
                }
                MouseArea { id: micDockMa; anchors.fill: parent; hoverEnabled: true; onClicked: { bridge.toggleVoiceMode(); registerHotspots(); hotspotTimer.start(); bridge.playSound("click") } }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttMic
                    visible: micDockMa.containsMouse
                    text: "Toggle Voice Mode"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttMic.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }

            // Input
            TextField {
                id: inputField
                Layout.fillWidth: true; Layout.preferredHeight: 36
                color: "#B0D0E0"
                placeholderText: "Message IRA…"
                placeholderTextColor: Qt.rgba(0, 1, 1, 0.18)
                font { pixelSize: 11; family: "Consolas" }
                enabled: !isProcessing
                background: Rectangle {
                    radius: 10; color: Qt.rgba(0, 0, 0, 0.28)
                    border.color: (inputField.activeFocus && root.active) ? Qt.rgba(0, 1, 1, 0.35) : Qt.rgba(0, 1, 1, 0.06)
                    border.width: 1
                }
                verticalAlignment: TextInput.AlignVCenter
                onAccepted: sendMsg()

                Keys.onPressed: function(event) {
                    if ((event.key === Qt.Key_V || event.key === Qt.Key_P) && (event.modifiers & Qt.ControlModifier)) {
                        if (bridge.handlePaste()) { event.accepted = true }
                    }
                    if (event.key === Qt.Key_Backslash) {
                        if (attachedImagesModel.count + attachedTextsModel.count > 0) {
                            attachedImagesModel.clear()
                            attachedTextsModel.clear()
                            attachedImage = ""
                            attachedLargeText = ""
                            attachedLargeTextPreview = ""
                            event.accepted = true
                        }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    propagateComposedEvents: true
                    onPressed: function(mouse) {
                        activateWindow()
                        inputField.forceActiveFocus()
                        mouse.accepted = false
                    }
                }
            }

            // Send / Stop
            Rectangle {
                id: sendBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : 1.0
                scale: isBooting ? 0.3 : 1.0
                readonly property bool isStopState: isProcessing || (isVoiceMode && (voiceState === "speaking" || voiceState === "thinking"))
                color: isStopState ? Qt.rgba(1, 0.27, 0.27, 0.12) : (sendDockMa.containsMouse ? Qt.rgba(0, 1, 1, 0.15) : Qt.rgba(0, 0, 0, 0.2))
                border.color: isStopState ? Qt.rgba(1, 0.27, 0.27, 0.35) : Qt.rgba(0, 1, 1, 0.22); border.width: 1
                Text {
                    anchors.centerIn: parent
                    text: sendBtn.isStopState ? "⏹" : "➤"
                    color: sendBtn.isStopState ? "#FF4444" : "#00FFFF"
                    font.pixelSize: 14
                }
                MouseArea { 
                    id: sendDockMa
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: { 
                        activateWindow()
                        if (sendBtn.isStopState) {
                            bridge.stopProcessing()
                        } else {
                            sendMsg()
                        }
                        bridge.playSound("click")
                    } 
                }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttSend
                    visible: sendDockMa.containsMouse
                    text: sendBtn.isStopState ? "Stop / Interrupt" : "Send Message"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttSend.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }

            // Sidebar toggle
            Rectangle {
                id: sidebarBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : 1.0
                scale: isBooting ? 0.3 : 1.0
                color: sidebarDockMa.containsMouse ? Qt.rgba(0, 0.5, 1, 0.12) : Qt.rgba(0, 0, 0, 0.2)
                border.color: rightPanelShown ? Qt.rgba(0, 0.5, 1, 0.35) : Qt.rgba(0, 0.5, 1, 0.12); border.width: 1
                Text { anchors.centerIn: parent; text: "⚙️"; font.pixelSize: 14 }
                MouseArea { id: sidebarDockMa; anchors.fill: parent; hoverEnabled: true; onClicked: { activateWindow(); rightPanelShown = !rightPanelShown; registerHotspots(); hotspotTimer.start(); bridge.playSound(rightPanelShown ? "expand" : "collapse") } }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttSidebar
                    visible: sidebarDockMa.containsMouse
                    text: "Toggle Settings"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttSidebar.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }

            // New Chat
            Rectangle {
                id: newChatBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : 1.0
                scale: isBooting ? 0.3 : 1.0
                color: newChatDockMa.containsMouse ? Qt.rgba(0, 1, 0.5, 0.12) : Qt.rgba(0, 0, 0, 0.2)
                border.color: Qt.rgba(0, 1, 0.5, 0.22); border.width: 1
                Text { anchors.centerIn: parent; text: "🔄"; font.pixelSize: 14 }
                MouseArea { id: newChatDockMa; anchors.fill: parent; hoverEnabled: true; onClicked: { bridge.newChat(getChatModelJson(), getNodeModelJson()); chatModel.clear(); nodeModel.clear(); attachedImagesModel.clear(); attachedTextsModel.clear(); attachedImage = ""; attachedLargeText = ""; attachedLargeTextPreview = ""; chatListView.forceScrollToBottom(); bridge.playSound("click") } }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttNewChat
                    visible: newChatDockMa.containsMouse
                    text: "New Conversation"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttNewChat.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }

            // Search Chat
            Rectangle {
                id: searchBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : 1.0
                scale: isBooting ? 0.3 : 1.0
                color: searchDockMa.containsMouse ? Qt.rgba(1, 0.8, 0, 0.12) : Qt.rgba(0, 0, 0, 0.2)
                border.color: Qt.rgba(1, 0.8, 0, 0.22); border.width: 1
                Text { anchors.centerIn: parent; text: "🔍"; font.pixelSize: 14 }
                MouseArea { id: searchDockMa; anchors.fill: parent; hoverEnabled: true; onClicked: { searchWindowShown = !searchWindowShown; if (searchWindowShown) bridge.listSessions(); bridge.playSound("click") } }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttSearch
                    visible: searchDockMa.containsMouse
                    text: "Search History"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttSearch.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }

            // Minimize dock
            Rectangle {
                id: minBtn
                width: 36; height: 36; radius: 18
                opacity: isBooting ? 0 : 1.0
                scale: isBooting ? 0.3 : 1.0
                color: minDockMa.containsMouse ? Qt.rgba(0, 1, 1, 0.12) : Qt.rgba(0, 0, 0, 0.2)
                border.color: Qt.rgba(0, 1, 1, 0.12); border.width: 1
                Text { anchors.centerIn: parent; text: "▼"; color: Qt.rgba(0, 1, 1, 0.35); font.pixelSize: 11 }
                MouseArea { id: minDockMa; anchors.fill: parent; hoverEnabled: true; onClicked: { activateWindow(); dockExpanded = false; chatPopupShown = false; registerHotspots(); hotspotTimer.start(); bridge.playSound("collapse") } }
                Behavior on color { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                Behavior on scale {
                    NumberAnimation { duration: 700; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
                }

                ToolTip {
                    id: ttMin
                    visible: minDockMa.containsMouse
                    text: "Minimize Dock"
                    delay: 400
                    y: -height - 8
                    x: parent.width / 2 - width / 2
                    contentItem: Text { text: ttMin.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
                    background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════
    //  DOCK MINIMIZED PILL
    // ═══════════════════════════════════════════════
    Rectangle {
        id: dockPill
        x: root.width / 2 - 52; y: root.height - bottomMargin
        width: 104; height: 22; radius: 11
        color: dockPillMa.containsMouse ? Qt.rgba(0, 1, 1, 0.14) : Qt.rgba(0, 0.024, 0.059, 0.78)
        border.color: Qt.rgba(0, 1, 1, 0.2); border.width: 1
        visible: !dockExpanded; z: 20
        scale: visible ? 1.0 : 0.5
        opacity: visible ? 1.0 : 0.0

        SequentialAnimation {
            id: pillPulse; loops: 3
            NumberAnimation { target: dockPill; property: "scale"; to: 1.12; duration: 200 }
            NumberAnimation { target: dockPill; property: "scale"; to: 1.0; duration: 200 }
        }

        Behavior on scale {
            NumberAnimation { duration: 500; easing.type: Easing.OutElastic; easing.amplitude: 1.0; easing.period: 0.5 }
        }
        Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }

        RowLayout {
            anchors.centerIn: parent; spacing: 5
            Rectangle { width: 5; height: 5; radius: 3; color: stateColor }
            Text { text: "IRA"; color: "#00FFFF"; font { pixelSize: 10; family: "Consolas"; bold: true; letterSpacing: 1 } }
            Text { text: "▲"; color: Qt.rgba(0, 1, 1, 0.35); font.pixelSize: 8 }
        }
        MouseArea { id: dockPillMa; anchors.fill: parent; hoverEnabled: true; onClicked: { activateWindow(); dockExpanded = true; registerHotspots(); hotspotTimer.start(); bridge.playSound("expand") } }

        ToolTip {
            id: ttPill
            visible: dockPillMa.containsMouse
            text: "Expand Dock"
            delay: 400
            y: -height - 8
            x: parent.width / 2 - width / 2
            contentItem: Text { text: ttPill.text; color: "#00FFFF"; font { family: "Consolas"; pixelSize: 9; bold: true } }
            background: Rectangle { color: Qt.rgba(0.02, 0.03, 0.05, 0.95); border.color: Qt.rgba(0, 0.96, 1, 0.3); border.width: 1; radius: 4 }
        }
    }

    // ═══════════════════════════════════════════════
    //  MAC-STYLE TOOL WINDOW
    // ═══════════════════════════════════════════════
    Rectangle {
        id: toolWindow
        x: root.width / 2 - 260; y: root.height / 2 - 190
        width: 520; height: 380; radius: 12
        color: Qt.rgba(0, 0.031, 0.071, 0.94)
        border.color: Qt.rgba(0, 1, 1, 0.14); border.width: 1
        visible: toolWindowShown; z: 40

        Rectangle {
            id: toolTitleBar
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: Qt.rgba(0, 0, 0, 0.4)

            Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 12; height: 12; color: parent.color }
            Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 12; height: 12; color: parent.color }

            MouseArea {
                anchors.fill: parent; z: 0
                property real offX; property real offY
                onPressed: function(mouse) { offX = mouse.x; offY = mouse.y }
                onPositionChanged: function(mouse) {
                    if (pressed) { toolWindow.x += mouse.x - offX; toolWindow.y += mouse.y - offY }
                }
            }

            RowLayout {
                anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 6; z: 1
                Rectangle {
                    width: 10; height: 10; radius: 5
                    color: closeToolMa.containsMouse ? "#FF5F57" : Qt.rgba(1, 0.37, 0.34, 0.55)
                    MouseArea { id: closeToolMa; anchors.fill: parent; hoverEnabled: true; onClicked: { toolWindowShown = false; registerHotspots(); hotspotTimer.start() } }
                }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(1, 0.74, 0.18, 0.35) }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(0.16, 0.79, 0.25, 0.35) }
            }

            Text {
                anchors.centerIn: parent; z: 1
                text: "ALL TOOLS"; color: Qt.rgba(0, 1, 1, 0.45)
                font { pixelSize: 10; family: "Consolas"; letterSpacing: 2; bold: true }
            }
        }

        ColumnLayout {
            anchors { top: toolTitleBar.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 20 }
            spacing: 10
            Item { Layout.fillHeight: true }
            Text { Layout.alignment: Qt.AlignHCenter; text: "⚡"; font.pixelSize: 40; opacity: 0.3 }
            Text { Layout.alignment: Qt.AlignHCenter; text: "Tools workspace"; color: Qt.rgba(0, 1, 1, 0.25); font { pixelSize: 13; family: "Consolas" } }
            Text { Layout.alignment: Qt.AlignHCenter; text: "Coming soon — reserved for future tool panels"; color: Qt.rgba(0, 1, 1, 0.12); font { pixelSize: 10; family: "Consolas" } }
            Item { Layout.fillHeight: true }
        }
    }

    // ═══════════════════════════════════════════════
    //  MAC-STYLE MEMORY WINDOW
    // ═══════════════════════════════════════════════
    Rectangle {
        id: memoryWindow
        x: root.width / 2 - 230; y: root.height / 2 - 160
        width: 460; height: 320; radius: 12
        color: Qt.rgba(0, 0.031, 0.071, 0.94)
        border.color: Qt.rgba(0, 1, 1, 0.14); border.width: 1
        visible: memoryWindowShown; z: 40

        Rectangle {
            id: memTitleBar
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: Qt.rgba(0, 0, 0, 0.4)

            Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 12; height: 12; color: parent.color }
            Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 12; height: 12; color: parent.color }

            MouseArea {
                anchors.fill: parent; z: 0
                property real offX; property real offY
                onPressed: function(mouse) { offX = mouse.x; offY = mouse.y }
                onPositionChanged: function(mouse) {
                    if (pressed) { memoryWindow.x += mouse.x - offX; memoryWindow.y += mouse.y - offY }
                }
            }

            RowLayout {
                anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 6; z: 1
                Rectangle {
                    width: 10; height: 10; radius: 5
                    color: closeMemMa.containsMouse ? "#FF5F57" : Qt.rgba(1, 0.37, 0.34, 0.55)
                    MouseArea { id: closeMemMa; anchors.fill: parent; hoverEnabled: true; onClicked: { memoryWindowShown = false; registerHotspots(); hotspotTimer.start() } }
                }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(1, 0.74, 0.18, 0.35) }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(0.16, 0.79, 0.25, 0.35) }
            }

            Text {
                anchors.centerIn: parent; z: 1
                text: "MEMORY"; color: Qt.rgba(0, 1, 1, 0.45)
                font { pixelSize: 10; family: "Consolas"; letterSpacing: 2; bold: true }
            }
        }

        ListView {
            id: memListView
            anchors { top: memTitleBar.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
            model: memoryModel; clip: true; spacing: 4

            ScrollBar.vertical: ScrollBar {
                id: memScroll
                policy: ScrollBar.AsNeeded
                active: memListView.activeFocus || memScroll.hovered || memScroll.active
                contentItem: Rectangle {
                    implicitWidth: 4; radius: 2
                    color: memScroll.pressed ? "#00FFFF" : Qt.rgba(0, 1, 1, 0.25)
                }
            }

            delegate: Rectangle {
                width: memListView.width; height: 52
                radius: 7
                color: memItemMa.containsMouse ? Qt.rgba(0, 1, 1, 0.06) : Qt.rgba(0, 1, 1, 0.015)
                border.color: memItemMa.containsMouse ? Qt.rgba(0, 1, 1, 0.1) : "transparent"
                border.width: 1

                ColumnLayout {
                    anchors { fill: parent; margins: 8 }
                    spacing: 2

                    Text {
                        text: "🧠 " + model.name
                        color: "#00FFFF"
                        font { pixelSize: 11; family: "Consolas"; bold: true }
                    }
                    Text {
                        text: model.preview
                        color: Qt.rgba(0, 1, 1, 0.30)
                        font { pixelSize: 9; family: "Consolas" }
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        maximumLineCount: 1
                    }
                }
                MouseArea { id: memItemMa; anchors.fill: parent; hoverEnabled: true }
                Behavior on color { ColorAnimation { duration: 120 } }
            }

            Text { anchors.centerIn: parent; visible: memoryModel.count === 0; text: "No memories saved yet"; color: Qt.rgba(0, 1, 1, 0.2); font { pixelSize: 11; family: "Consolas" } }
        }
    }

    // ═══════════════════════════════════════════════
    //  PHONE CONNECTION BRIDGE WINDOW
    // ═══════════════════════════════════════════════
    Rectangle {
        id: phoneBridgeWindow
        x: root.width / 2 - 180; y: root.height / 2 - 180
        width: 360; height: 360; radius: 12
        color: Qt.rgba(0, 0.031, 0.071, 0.96)
        border.color: Qt.rgba(0, 1, 1, 0.18); border.width: 1
        visible: phoneBridgeWindowShown; z: 40

        Rectangle {
            id: phoneTitleBar
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: Qt.rgba(0, 0, 0, 0.4)

            Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 12; height: 12; color: parent.color }
            Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 12; height: 12; color: parent.color }

            MouseArea {
                anchors.fill: parent; z: 0
                property real offX; property real offY
                onPressed: function(mouse) { offX = mouse.x; offY = mouse.y }
                onPositionChanged: function(mouse) {
                    if (pressed) { phoneBridgeWindow.x += mouse.x - offX; phoneBridgeWindow.y += mouse.y - offY }
                }
            }

            RowLayout {
                anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 6; z: 1
                Rectangle {
                    width: 10; height: 10; radius: 5
                    color: closePhoneMa.containsMouse ? "#FF5F57" : Qt.rgba(1, 0.37, 0.34, 0.55)
                    MouseArea { id: closePhoneMa; anchors.fill: parent; hoverEnabled: true; onClicked: { phoneBridgeWindowShown = false; registerHotspots(); hotspotTimer.start() } }
                }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(1, 0.74, 0.18, 0.35) }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(0.16, 0.79, 0.25, 0.35) }
            }

            Text {
                anchors.centerIn: parent; z: 1
                text: "PHONE CONNECTION BRIDGE"; color: Qt.rgba(0, 1, 1, 0.45)
                font { pixelSize: 9; family: "Consolas"; letterSpacing: 1.5; bold: true }
            }
        }

        ColumnLayout {
            anchors { top: phoneTitleBar.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 16 }
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: "Scan QR code with your phone camera to link your phone, or open the link manually."
                color: Qt.rgba(0, 1, 1, 0.4)
                font { pixelSize: 9; family: "Consolas" }
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            // QR Code display container
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                width: 180; height: 180; radius: 8
                color: "white"
                border.color: Qt.rgba(0, 1, 1, 0.3); border.width: 1

                Image {
                    anchors.fill: parent
                    anchors.margins: 6
                    source: phoneBridgeQr
                    smooth: true
                    cache: false
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                Text {
                    Layout.fillWidth: true
                    text: "Manual URL: " + phoneBridgeUrl
                    color: "#00d4ff"
                    font { pixelSize: 9; family: "Consolas"; bold: true }
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: "Connection PIN: " + phoneBridgePin
                    color: "#00ff88"
                    font { pixelSize: 10; family: "Consolas"; bold: true }
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }



    // ═══════════════════════════════════════════════
    //  SEARCH CHAT WINDOW
    // ═══════════════════════════════════════════════
    Rectangle {
        id: searchWindow
        x: (root.width - 360) / 2; y: (root.height - 480) / 2
        width: 360; height: 480; radius: 14
        color: Qt.rgba(0, 0.024, 0.059, 0.94)
        border.color: Qt.rgba(1, 0.8, 0, 0.25); border.width: 1.5
        visible: searchWindowShown; z: 40

        Rectangle {
            id: searchTitleBar
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: Qt.rgba(0, 0, 0, 0.4)
            radius: 14

            Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 14; height: 14; color: parent.color }
            Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 14; height: 14; color: parent.color }

            MouseArea {
                anchors.fill: parent; z: 0
                property real offX; property real offY
                onPressed: function(mouse) { offX = mouse.x; offY = mouse.y }
                onPositionChanged: function(mouse) {
                    if (pressed) { searchWindow.x += mouse.x - offX; searchWindow.y += mouse.y - offY }
                }
            }

            RowLayout {
                anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 6; z: 1
                Rectangle {
                    width: 10; height: 10; radius: 5
                    color: closeSearchMa.containsMouse ? "#FF5F57" : Qt.rgba(1, 0.37, 0.34, 0.55)
                    MouseArea { id: closeSearchMa; anchors.fill: parent; hoverEnabled: true; onClicked: { searchWindowShown = false } }
                }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(1, 0.74, 0.18, 0.35) }
                Rectangle { width: 10; height: 10; radius: 5; color: Qt.rgba(0.16, 0.79, 0.25, 0.35) }
            }

            Text {
                anchors.centerIn: parent; z: 1
                text: "CHAT HISTORY"; color: Qt.rgba(1, 0.8, 0, 0.55)
                font { pixelSize: 10; family: "Consolas"; letterSpacing: 2; bold: true }
            }
        }

        // Search input
        TextField {
            id: searchField
            anchors { top: searchTitleBar.bottom; left: parent.left; right: parent.right; margins: 10; topMargin: 8 }
            height: 30
            color: "#B0D0E0"
            placeholderText: "🔍 Search conversations..."
            placeholderTextColor: Qt.rgba(1, 0.8, 0, 0.2)
            font { pixelSize: 11; family: "Consolas" }
            background: Rectangle {
                radius: 8; color: Qt.rgba(0, 0, 0, 0.3)
                border.color: searchField.activeFocus ? Qt.rgba(1, 0.8, 0, 0.35) : Qt.rgba(1, 0.8, 0, 0.08)
                border.width: 1
            }
            onTextChanged: {
                searchDebounce.stop()
                if (text.trim().length > 0) {
                    searchDebounce.restart()
                } else {
                    bridge.listSessions()
                }
            }
        }

        Timer {
            id: searchDebounce
            interval: 300
            repeat: false
            onTriggered: bridge.searchChats(searchField.text.trim())
        }

        // Flat list model: each item is either a "folder" or a "chat"
        ListModel { id: searchResultsModel }

        // Sessions list — flat list with section headers
        ListView {
            id: searchListView
            anchors { top: searchField.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10; topMargin: 6 }
            clip: true; spacing: 2
            model: searchResultsModel

            section.property: "section"
            section.delegate: Rectangle {
                width: searchListView.width; height: 28; radius: 6
                color: Qt.rgba(1, 0.8, 0, 0.06)
                Text {
                    anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                    text: "📁 " + section
                    color: Qt.rgba(1, 0.8, 0, 0.6)
                    font { pixelSize: 11; family: "Consolas"; bold: true }
                }
            }

            delegate: Rectangle {
                width: searchListView.width; height: 36; radius: 5
                color: chatFileMa.containsMouse ? Qt.rgba(1, 0.8, 0, 0.08) : "transparent"

                Column {
                    anchors { left: parent.left; leftMargin: 20; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    spacing: 1

                    Row {
                        spacing: 6
                        Text {
                            text: "💬"
                            font.pixelSize: 10
                        }
                        Text {
                            text: model.display || ""
                            color: Qt.rgba(0, 1, 1, 0.7)
                            font { pixelSize: 11; family: "Consolas" }
                            elide: Text.ElideRight
                            width: searchListView.width - 60
                        }
                    }

                    Text {
                        text: model.snippet || ""
                        visible: model.snippet !== undefined && model.snippet !== ""
                        color: Qt.rgba(1, 0.8, 0, 0.3)
                        font { pixelSize: 9; family: "Consolas" }
                        elide: Text.ElideRight
                        width: searchListView.width - 60
                        maximumLineCount: 1
                    }
                }

                MouseArea {
                    id: chatFileMa
                    anchors.fill: parent; hoverEnabled: true
                    onClicked: {
                        bridge.loadChat(model.filepath)
                        searchWindowShown = false
                        chatPopupShown = true
                        registerHotspots(); hotspotTimer.start()
                    }
                }
                Behavior on color { ColorAnimation { duration: 80 } }
            }

            Text { anchors.centerIn: parent; visible: searchResultsModel.count === 0; text: "No conversations saved yet"; color: Qt.rgba(1, 0.8, 0, 0.2); font { pixelSize: 11; family: "Consolas" } }
        }
    }

    // ═══════════════════════════════════════════════
    //  VOICE MODE OVERLAY (compact floating window)
    // ═══════════════════════════════════════════════
    Rectangle {
        id: voiceOverlay
        visible: isVoiceMode
        width: 200; height: 220
        x: (root.width - width) / 2
        y: root.height - height - 180
        radius: 16
        color: Qt.rgba(0.04, 0.06, 0.1, 0.92)
        border.color: Qt.rgba(0, 1, 1, 0.15); border.width: 1
        z: 100
        opacity: isVoiceMode ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }

        // State label
        Text {
            id: voiceStateLabel
            anchors { top: parent.top; topMargin: 14; horizontalCenter: parent.horizontalCenter }
            text: {
                if (voiceState === "speaking") return "🔊 Speaking"
                else if (voiceState === "thinking") return "⚡ Thinking..."
                else if (voiceState === "connecting") return "📡 Connecting..."
                else return "🎤 Listening"
            }
            color: {
                if (voiceState === "speaking") return "#00FF88"
                else if (voiceState === "thinking") return "#FFAA00"
                else if (voiceState === "connecting") return "#88A0B0"
                else return "#00FFFF"
            }
            font { pixelSize: 11; family: "Consolas"; bold: true }
        }

        // Animated orb — smaller, compact
        Item {
            anchors { top: voiceStateLabel.bottom; topMargin: 8; horizontalCenter: parent.horizontalCenter }
            width: 100; height: 100

            // Ripple rings
            Repeater {
                model: 3
                Rectangle {
                    x: parent.width / 2 - width / 2; y: parent.height / 2 - height / 2
                    width: 40 + index * 25; height: 40 + index * 25
                    radius: (40 + index * 25) / 2
                    color: "transparent"
                    border {
                        color: voiceState === "speaking" ? Qt.rgba(0, 1, 0.5, 0.2 + index * 0.08) :
                               voiceState === "thinking" ? Qt.rgba(1, 0.7, 0, 0.2 + index * 0.08) :
                               voiceState === "connecting" ? Qt.rgba(0.5, 0.6, 0.7, 0.12 + index * 0.05) :
                               Qt.rgba(0, 1, 1, 0.2 + index * 0.08)
                        width: 1.2
                    }
                    SequentialAnimation on scale {
                        running: true; loops: Animation.Infinite
                        NumberAnimation { from: 0.5; to: 1.6; duration: 1800 + index * 200; easing.type: Easing.InOutQuad }
                        NumberAnimation { from: 1.6; to: 0.5; duration: 1800 + index * 200; easing.type: Easing.InOutQuad }
                    }
                    SequentialAnimation on opacity {
                        running: true; loops: Animation.Infinite
                        NumberAnimation { from: 0.7; to: 0.0; duration: 1800 + index * 200; easing.type: Easing.InOutQuad }
                        NumberAnimation { from: 0.0; to: 0.7; duration: 1800 + index * 200; easing.type: Easing.InOutQuad }
                    }
                }
            }

            // Center orb
            Rectangle {
                anchors.centerIn: parent
                width: 60; height: 60; radius: 30
                gradient: Gradient {
                    GradientStop { position: 0.0; color: voiceState === "speaking" ? Qt.rgba(0, 1, 0.5, 0.3) :
                                  voiceState === "thinking" ? Qt.rgba(1, 0.7, 0, 0.3) :
                                  voiceState === "connecting" ? Qt.rgba(0.5, 0.6, 0.7, 0.15) :
                                  Qt.rgba(0, 1, 1, 0.3) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                SequentialAnimation on scale {
                    running: true; loops: Animation.Infinite
                    NumberAnimation { from: 0.85; to: 1.15; duration: 1000; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1.15; to: 0.85; duration: 1000; easing.type: Easing.InOutSine }
                }
            }

            // Busy indicator spinner for connecting state
            Text {
                id: voiceConnectingSpinner
                anchors.centerIn: parent
                text: "🌀"
                font.pixelSize: 32
                color: "#00FFFF"
                visible: voiceState === "connecting"
                
                RotationAnimation on rotation {
                    running: voiceState === "connecting"
                    loops: Animation.Infinite
                    from: 0
                    to: 360
                    duration: 1200
                }
            }

            // Mic icon (only visible when fully connected)
            Text {
                anchors.centerIn: parent
                text: "🎤"
                font.pixelSize: 26
                visible: voiceState !== "connecting"
            }
        }

        // Exit hint
        Text {
            id: exitLabel
            anchors { bottom: parent.bottom; bottomMargin: 10; horizontalCenter: parent.horizontalCenter }
            text: "Esc to exit"
            color: Qt.rgba(0, 1, 1, 0.2)
            font { pixelSize: 9; family: "Consolas" }
        }

        // Voice transcription text — shows what IRA said (from audio transcription)
        Text {
            id: voiceTranscriptLabel
            anchors { bottom: exitLabel.top; bottomMargin: 6; horizontalCenter: parent.horizontalCenter }
            width: parent.width - 24
            visible: voiceTranscriptText.length > 0
            text: voiceTranscriptText
            color: Qt.rgba(1, 1, 1, 0.5)
            font { pixelSize: 9; family: "Consolas" }
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }

        // Close button
        Rectangle {
            anchors { top: parent.top; right: parent.right; topMargin: 6; rightMargin: 6 }
            width: 28; height: 28; radius: 14
            z: 10
            color: closeVoiceMa.containsMouse ? Qt.rgba(1, 0.27, 0.27, 0.4) : Qt.rgba(0, 0, 0, 0.3)
            border.color: Qt.rgba(1, 0.27, 0.27, 0.3); border.width: 1
            Text { anchors.centerIn: parent; text: "✕"; color: "#FF4444"; font { pixelSize: 11; bold: true } }
            MouseArea { id: closeVoiceMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.toggleVoiceMode() }
        }

        Connections {
            target: bridge
            function onRequestAutoSave() {
                bridge.autoSave(getChatModelJson(), getNodeModelJson())
            }
            function onVoiceStateChanged(state) {
                voiceState = state
                if (isVoiceMode) {
                    if (state === "speaking") {
                        avatarState = "talking"
                    } else if (state === "thinking") {
                        avatarState = "thinking"
                    } else if (state === "listening") {
                        avatarState = "listening"
                    } else if (state === "connecting") {
                        avatarState = "thinking"
                    }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════
    //  GESTURE MIRRORING TIMERS — auto-reset after 1.5s
    // ═══════════════════════════════════════════════
    Timer { id: smileResetTimer; interval: 1500; onTriggered: root.userSmiling = false }
    Timer { id: frownResetTimer; interval: 1500; onTriggered: root.userFrowning = false }
    Timer { id: mouthResetTimer; interval: 1500; onTriggered: root.userMouthOpen = false }
    Timer { id: blinkResetTimer; interval: 400; onTriggered: root.userBlinking = false }
    Timer { id: browsResetTimer; interval: 1500; onTriggered: root.userBrowsRaised = false }
    Timer { id: nodResetTimer; interval: 1500; onTriggered: root.userHeadNod = false }
    Timer { id: shakeResetTimer; interval: 1500; onTriggered: root.userHeadShake = false }
    Timer { id: gestureResetTimer; interval: 2000; onTriggered: avatarState = "idle" }

    // ═══════════════════════════════════════════════
    //  BRIDGE CONNECTIONS
    // ═══════════════════════════════════════════════
    Connections {
        target: bridge

        function onDockExpansionRequested(expanded) {
            dockExpanded = expanded
            registerHotspots()
            hotspotTimer.start()
        }

        function onTimeUpdated(timeStr, dateStr) {}

        function onAvatarExpressionChanged(expression) {
            iraAvatar.avatarExpression = expression
            root.currentExpression = expression
        }

        function onThemeChanged(theme) {
            root.changeTheme(theme)
        }

        function onAudioLevelChanged(level) {
            root.audioLevel = level
        }

        function onMouseMoved(x, y) {
            root.mouseX = x
            root.mouseY = y
        }

        function onConsoleOutput(line) {
            root.consoleLog += line + "\n"
        }

        function onNodeEventReceived(jsonPayload) {
            var payload = JSON.parse(jsonPayload)
            if (payload.action === "create") {
                showNodes = true
                var found = false
                for (var i = 0; i < nodeModel.count; i++) {
                    if (nodeModel.get(i).nodeId === payload.id) {
                        nodeModel.setProperty(i, "title", payload.title)
                        nodeModel.setProperty(i, "content", payload.content)
                        if (payload.x !== undefined && payload.x !== null) nodeModel.setProperty(i, "nodeX", payload.x)
                        if (payload.y !== undefined && payload.y !== null) nodeModel.setProperty(i, "nodeY", payload.y)
                        if (payload.width !== undefined && payload.width !== null) nodeModel.setProperty(i, "nodeWidth", payload.width)
                        if (payload.height !== undefined && payload.height !== null) nodeModel.setProperty(i, "nodeHeight", payload.height)
                        found = true
                        break
                    }
                }
                if (!found) {
                    nodeModel.append({
                        "nodeId": payload.id, "title": payload.title, "content": payload.content,
                        "nodeX": (payload.x !== undefined && payload.x !== null) ? payload.x : (root.width - 750) / 2,
                        "nodeY": (payload.y !== undefined && payload.y !== null) ? payload.y : (root.height - 500) / 2,
                        "nodeWidth": payload.width || 750, "nodeHeight": payload.height || 500, "zoomScale": 1.0
                    })
                }
                registerHotspots()
            } else if (payload.action === "edit") {
                showNodes = true
                for (var i = 0; i < nodeModel.count; i++) {
                    if (nodeModel.get(i).nodeId === payload.id) {
                        if (payload.title !== undefined && payload.title !== null) nodeModel.setProperty(i, "title", payload.title)
                        if (payload.content !== undefined && payload.content !== null) nodeModel.setProperty(i, "content", payload.content)
                        if (payload.x !== undefined && payload.x !== null) nodeModel.setProperty(i, "nodeX", payload.x)
                        if (payload.y !== undefined && payload.y !== null) nodeModel.setProperty(i, "nodeY", payload.y)
                        if (payload.width !== undefined && payload.width !== null) nodeModel.setProperty(i, "nodeWidth", payload.width)
                        if (payload.height !== undefined && payload.height !== null) nodeModel.setProperty(i, "nodeHeight", payload.height)
                        break
                    }
                }
                registerHotspots()
            } else if (payload.action === "delete") {
                for (var i = 0; i < nodeModel.count; i++) {
                    if (nodeModel.get(i).nodeId === payload.id) {
                        nodeModel.remove(i)
                        break
                    }
                }
                registerHotspots()
            }
            bridge.autoSave(getChatModelJson(), getNodeModelJson())
        }

        function onStatusChanged(state, label) {
            stateText = label
            var cmap = { "idle": "#00ff88", "thinking": "#ffaa00", "tool": "#00FFFF", "error": "#ff4444", "capturing": "#ffaa00", "voice": "#00FFFF" }
            stateColor = cmap[state] || "#888888"

            var amap = { "idle": "idle", "thinking": "thinking", "tool": "thinking", "error": "idle", "capturing": "listening", "voice": "listening" }
            avatarState = amap[state] || "idle"
        }

        function onAvatarStateChanged(state) {
            avatarState = state
        }

        function onSystemStatsUpdated(jsonStats) {
            var s = JSON.parse(jsonStats)
            cpuVal = s.cpu || 0
            ramVal = s.ram || 0
            batVal = (s.battery !== null && s.battery !== undefined) ? s.battery : 0
            ramUsedStr = s.ram_used || "?"
            ramTotalStr = s.ram_total || "?"
            isCharging = s.charging || false
        }

        function onSettingsUpdated(json) {
            var settings = JSON.parse(json)
            autoDetectEnabled = settings.location.auto_detect
            gesturesEnabled = settings.gestures ? (settings.gestures.enabled !== false) : true
            autoScreenshotEnabled = settings.screenshots ? (settings.screenshots.auto_screenshot !== false) : true
            reasoningEnabled = settings.reasoning ? (settings.reasoning.enabled !== false) : true
            reasoningLevel = settings.reasoning ? (settings.reasoning.level || "high") : "high"
            userLat = settings.location.lat
            userLng = settings.location.lng
            userLocation = settings.location.city || "Unknown"
            locationText.text = userLocation
            latInput.text = userLat.toString()
            lngInput.text = userLng.toString()
            var theme = (settings.avatar && settings.avatar.theme) ? settings.avatar.theme : "cyan"
            root.changeTheme(theme)
        }

        function onProcessingChanged(p) {
            isProcessing = p
            if (!p) inputField.forceActiveFocus()
        }

        function onAssistantResponseChunk(partialHtml) {
            // Skip chat bubble creation during voice mode — voice has its own display
            if (isVoiceMode) return
            if (chatModel.count === 0) return
            updateIraTextChunk(partialHtml)
            chatListView.smartScroll()
        }

        function onAssistantResponse(html) {
            // Handle user message from Python (voice mode or direct sendMessage)
            if (html.indexOf("__user__:") === 0) {
                var userHtml = html.substring(8)
                appendUserMessage(userHtml, "", "")
                appendIraMessage()
                chatPopupShown = true
                registerHotspots()
                hotspotTimer.start()
                return
            }

            // Skip chat bubble creation during voice mode
            if (isVoiceMode) {
                // Still update avatar state for animation
                if (html.length > 0) {
                    stateText = "Talking"
                    stateColor = "#00FF88"
                    avatarState = "talking"
                    var charCount = stripHtml(html).length
                    var duration = Math.min(10000, Math.max(3000, charCount * 60))
                    talkingTimer.interval = duration
                    talkingTimer.start()
                }
                return
            }

            currentIraText = html
            finalizeIraMessage(html)

            stateText = "Ready"
            stateColor = "#00ff88"

            chatPopupShown = true
            if (!dockExpanded) pillPulse.start()

            registerHotspots()
            hotspotTimer.start()
            bridge.autoSave(getChatModelJson(), getNodeModelJson())
        }

        function onScreenshotReceived(path) {
            if (chatModel.count > 0) {
                var idx = chatModel.count - 1
                chatModel.setProperty(idx, "imagePath", path)
                chatListView.smartScroll()
            }
        }

        function onPhaseChanged(icon, label) {
            if (label && label.length > 0) {
                phaseIcon = icon
                phaseLabel = label
                stateText = icon + " " + label
                stateColor = "#00d4ff"
            } else {
                phaseIcon = ""
                phaseLabel = ""
                stateText = "Ready"
                stateColor = "#00ff88"
            }
        }

        function onThoughtReceived(html) {
            stateText = "Thinking…"
            stateColor = "#FFAA00"
            var txt = stripHtml(html)
            if (txt.length > 0) {
                updateThinkingMessage(txt)
                chatListView.smartScroll()
            }
        }

        function onToolCalled(name, argsText, argsJson) {
            stateText = "🔧 " + name
            stateColor = "#00FFFF"
            appendToolMessage(name, argsText || "")
            chatListView.smartScroll()
        }

        function onToolResult(name, result) {
            var res = stripHtml(result)
            if (res.length > 200) res = res.substring(0, 200) + "..."
            updateLastToolResult(res)
        }

        function onErrorOccurred(msg) {
            stateText = "Error"
            stateColor = "#FF4444"
            currentIraText = "⚠ " + msg
            finalizeIraMessage("⚠ " + msg)
            chatPopupShown = true
            registerHotspots()
            hotspotTimer.start()
        }

        function onVoiceModeChanged(active) {
            isVoiceMode = active
            if (active) {
                stateText = "🎤 Listening"
                stateColor = "#00FFFF"
                avatarState = "listening"
                chatPopupShown = false
                voiceTranscriptText = ""
                registerHotspots()
                hotspotTimer.start()
            } else {
                stateText = "Ready"
                stateColor = "#00ff88"
                avatarState = "idle"
                voiceTranscriptText = ""
            }
        }

        function onVoiceTranscribed(text) {
            inputField.text = text
            transcriptClearTimer.restart()
        }

        function onVoiceResponseChunk(text) {
            // Voice-only transcription — shows in voice overlay, NOT in chat bubbles
            voiceTranscriptText = text
        }

        function onVoiceError(msg) {
            finalizeIraMessage("⚠️ Voice: " + msg)
            chatPopupShown = true
            registerHotspots()
            hotspotTimer.start()
        }

        // ── GESTURE MIRRORING ──────────────────────
        function onGestureDetected(name, confidence) {
            userGesture = name
            // Hand gesture reactions — brief avatar state changes
            if (name === "wave") {
                avatarState = "listening"
                gestureResetTimer.restart()
            } else if (name === "thumbs_up") {
                avatarState = "talking"
                gestureResetTimer.restart()
            } else if (name === "fist") {
                avatarState = "thinking"
                gestureResetTimer.restart()
            } else if (name === "peace" || name === "rock") {
                avatarState = "talking"
                gestureResetTimer.restart()
            }
        }

        function onFaceStateChanged(expression, confidence) {
            // Face expression mirroring — avatar mimics user's face
            if (expression === "smile") {
                userSmiling = true
                smileResetTimer.restart()
            } else if (expression === "frown") {
                userFrowning = true
                frownResetTimer.restart()
            } else if (expression === "open_mouth") {
                userMouthOpen = true
                mouthResetTimer.restart()
            } else if (expression === "blink_both" || expression === "blink_left" || expression === "blink_right") {
                userBlinking = true
                blinkResetTimer.restart()
            } else if (expression === "raise_eyebrows") {
                userBrowsRaised = true
                browsResetTimer.restart()
            } else if (expression === "head_nod") {
                userHeadNod = true
                nodResetTimer.restart()
            } else if (expression === "head_shake") {
                userHeadShake = true
                shakeResetTimer.restart()
            }
        }

        function onGestureLogEntry(jsonStr) {
            var entry = JSON.parse(jsonStr)
            var msg = "[" + (entry.time || "") + "] Gesture Detected: " + (entry.name || "?") + " (conf: " + (entry.confidence || 0) + ") -> Action: " + (entry.action || "none")
            if (root.consoleLog.length > 0) {
                root.consoleLog += "\n" + msg
            } else {
                root.consoleLog = msg
            }
        }

        function onCameraFrameUpdate(base64) {
            cameraFrameBase64 = base64
        }

        function onGestureOverlayEvent(jsonStr) {
            handleGestureOverlayEvent(jsonStr)
        }

        function onGestureControlState(jsonStr) {
            var s = JSON.parse(jsonStr)
            ctrlEngaged = !!s.engaged
            ctrlArmed = !!s.armed
            ctrlAction = s.action || "none"
            // Controller already mirrors X (in hud_overlay._mirror_hand) so its
            // cursor + trail + bursts are all in mirrored space, matching the
            // mirrored camera preview. We just map normalized -> HUD px here.
            var nx = s.cursor_x != null ? s.cursor_x : 0.5
            var ny = s.cursor_y != null ? s.cursor_y : 0.5
            ctrlCursorX = nx * root.width
            ctrlCursorY = ny * root.height
            ctrlTrail = s.trail || []
            var newBursts = s.bursts || []
            if (newBursts.length > 0) {
                ctrlBursts = ctrlBursts.concat(newBursts)
                burstClearTimer.restart()
            }
        }

        function onImagePasted(urlPath) {
            if (attachedImagesModel.count >= maxAttachments) return
            attachedImagesModel.append({ "path": urlPath })
            attachedImage = urlPath  // legacy compat
            chatPopupShown = true
            registerHotspots()
            hotspotTimer.start()
        }

        function onLargeTextPasted(preview, fullText) {
            if (attachedTextsModel.count >= maxAttachments) return
            attachedTextsModel.append({ "preview": preview, "fullText": fullText })
            attachedLargeTextPreview = preview  // legacy compat
            attachedLargeText = fullText         // legacy compat
            chatPopupShown = true
            registerHotspots()
            hotspotTimer.start()
        }

        function onShortTextPasted(text) {
            inputField.insert(inputField.cursorPosition, text)
        }

        function onHudHidden() {
            root.visible = false
        }

        function onSessionsListed(jsonStr) {
            searchResultsModel.clear()
            var sessions = JSON.parse(jsonStr)
            for (var i = 0; i < sessions.length; i++) {
                var s = sessions[i]
                for (var j = 0; j < s.files.length; j++) {
                    var f = s.files[j]
                    searchResultsModel.append({
                        "section": s.display,
                        "display": f.display,
                        "filepath": f.filepath,
                        "snippet": ""
                    })
                }
            }
        }

        function onSearchResults(jsonStr) {
            searchResultsModel.clear()
            var results = JSON.parse(jsonStr)
            if (results.length === 0) {
                return
            }
            // Group by folder
            var folders = {}
            var folderOrder = []
            for (var i = 0; i < results.length; i++) {
                var r = results[i]
                var folder = r.folder || "Other"
                if (!folders[folder]) {
                    folders[folder] = []
                    folderOrder.push(folder)
                }
                folders[folder].push(r)
            }
            for (var k = 0; k < folderOrder.length; k++) {
                var folderName = folderOrder[k]
                var items = folders[folderName]
                for (var m = 0; m < items.length; m++) {
                    var item = items[m]
                    searchResultsModel.append({
                        "section": folderName,
                        "display": item.display,
                        "filepath": item.filepath,
                        "snippet": item.snippet || ""
                    })
                }
            }
        }

        function onChatLoaded(jsonStr) {
            var data = JSON.parse(jsonStr)
            chatModel.clear()
            
            // Re-populate nodeModel if nodes are present
            nodeModel.clear()
            if (data.nodes && data.nodes.length > 0) {
                for (var n = 0; n < data.nodes.length; n++) {
                    var node = data.nodes[n]
                    nodeModel.append({
                        "nodeId": node.nodeId || node.id,
                        "title": node.title || "",
                        "content": node.content || "",
                        "nodeX": node.nodeX !== undefined ? node.nodeX : (node.x !== undefined ? node.x : (root.width - 750) / 2),
                        "nodeY": node.nodeY !== undefined ? node.nodeY : (node.y !== undefined ? node.y : (root.height - 500) / 2),
                        "nodeWidth": node.nodeWidth || node.width || 750,
                        "nodeHeight": node.nodeHeight || node.height || 500,
                        "zoomScale": node.zoomScale || 1.0
                    })
                }
            }

            // Re-populate chatModel — full rich schema (everything)
            if (data.chat_model_data && data.chat_model_data.length > 0) {
                for (var i = 0; i < data.chat_model_data.length; i++) {
                    var item = data.chat_model_data[i]
                    chatModel.append({
                        "sender": item.sender || "ira",
                        "text": item.text || "",
                        "imagePath": item.imagePath || "",
                        "largeText": item.largeText || "",
                        "toolLogs": item.toolLogs || "",
                        "isThinking": !!item.isThinking,
                        "toolName": item.toolName || "",
                        "toolArgs": item.toolArgs || "",
                        "toolResult": item.toolResult || ""
                    })
                }
            } else {
                // Backward compatibility if chat_model_data is not present
                var msgs = data.messages || data
                if (Array.isArray(msgs)) {
                    for (var j = 0; j < msgs.length; j++) {
                        var m = msgs[j]
                        var isUser = m.role === "user"
                        chatModel.append({
                            "sender": isUser ? "user" : "ira",
                            "text": isUser ? (m.text || "") : (m.html || m.text || ""),
                            "imagePath": m.imagePath || "",
                            "largeText": m.largeText || "",
                            "toolLogs": m.toolLogs || "",
                            "isThinking": false,
                            "toolName": m.toolName || "",
                            "toolArgs": m.toolArgs || "",
                            "toolResult": m.toolResult || ""
                        })
                    }
                }
            }
            chatListView.forceScrollToBottom()
            registerHotspots()
            hotspotTimer.start()
        }
    }

    Timer {
        id: transcriptClearTimer
        interval: 1200
        repeat: false
        onTriggered: inputField.text = ""
    }

    Timer {
        id: gestureToastTimer
        interval: 1400
        repeat: false
        onTriggered: gestureToastShown = false
    }

    // Clears burst particle delegates once their ~600ms animation finishes
    Timer {
        id: burstClearTimer
        interval: 650
        repeat: false
        onTriggered: ctrlBursts = []
    }

    // Memory + Todo list from bridge
    Connections {
        target: bridge
        function onMemoryListUpdated(jsonStr) {
            memoryModel.clear()
            var files = JSON.parse(jsonStr)
            for (var i = 0; i < files.length; i++) {
                memoryModel.append({ "name": files[i].name, "preview": files[i].preview })
            }
        }

        function onTodoListUpdated(jsonStr) {
            todoModel.clear()
            try {
                var tasks = JSON.parse(jsonStr)
                for (var i = 0; i < tasks.length; i++) {
                    var t = tasks[i]
                    todoModel.append({
                        "id": t.id !== undefined ? t.id : i,
                        "task": t.task || t.text || "",
                        "text": t.task || t.text || "",
                        "completed": t.completed || false
                    })
                }
            } catch(e) {}
        }
    }

    // ═══════════════════════════════════════════════
    //  KEYBOARD SHORTCUTS
    // ═══════════════════════════════════════════════
    Shortcut {
        sequence: "Escape"
        onActivated: {
            if (isVoiceMode) bridge.toggleVoiceMode()
            else if (toolWindowShown) { toolWindowShown = false; registerHotspots(); hotspotTimer.start() }
            else if (memoryWindowShown) { memoryWindowShown = false; registerHotspots(); hotspotTimer.start() }
            else if (leftPanelShown) { leftPanelShown = false; registerHotspots(); hotspotTimer.start() }
            else if (searchWindowShown) { searchWindowShown = false }
            else if (chatPopupShown) { chatPopupShown = false; registerHotspots(); hotspotTimer.start() }
            else bridge.hideHUD(getChatModelJson(), getNodeModelJson())
        }
    }


    // ═══════════════════════════════════════════════
    //  FLOATING NODES CONTAINER
    // ═══════════════════════════════════════════════
    Item {
        id: nodesContainer
        anchors.fill: parent
        visible: showNodes
        z: 8

        Repeater {
            model: nodeModel
            delegate: Rectangle {
                id: nodeRect
                x: model.nodeX
                y: model.nodeY
                width: model.nodeWidth
                height: model.nodeHeight
                radius: 10
                color: Qt.rgba(0.02, 0.04, 0.08, 0.94)
                border.color: Qt.rgba(0.0, 1.0, 1.0, 0.35)
                border.width: 1.5

                Rectangle {
                    anchors.fill: parent; radius: parent.radius; color: "transparent"
                    border.color: Qt.rgba(0, 1, 1, 0.1); border.width: 4; z: -1
                }

                Rectangle {
                    id: nodeHeader
                    width: parent.width; height: 32
                    color: Qt.rgba(0.0, 0.3, 0.3, 0.3)
                    radius: 10; clip: true

                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 5; color: parent.color }

                    Text {
                        anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                        text: model.title; color: "#00ffff"
                        font { bold: true; family: "Consolas"; pixelSize: 12 }
                    }

                    Row {
                        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; spacing: 6

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: (model.zoomScale * 100).toFixed(0) + "%"
                            color: Qt.rgba(0.0, 1.0, 1.0, 0.4)
                            font { family: "Consolas"; pixelSize: 10 }
                        }

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 18; height: 18; radius: 4
                            color: closeNodeMa.containsMouse ? Qt.rgba(1, 0, 0, 0.35) : "transparent"
                            Text { anchors.centerIn: parent; text: "×"; color: "#ff3366"; font.bold: true; font.pixelSize: 13 }
                            MouseArea {
                                id: closeNodeMa; anchors.fill: parent; hoverEnabled: true
                                onClicked: { nodeModel.remove(index); registerHotspots(); hotspotTimer.start(); bridge.autoSave(getChatModelJson(), getNodeModelJson()) }
                            }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent; anchors.rightMargin: 60
                        property point clickPos: "0,0"
                        onPressed: (mouse) => { clickPos = Qt.point(mouse.x, mouse.y); activateWindow() }
                        onPositionChanged: (mouse) => {
                            var delta = Qt.point(mouse.x - clickPos.x, mouse.y - clickPos.y)
                            var newX = Math.max(0, Math.min(root.width - nodeRect.width, nodeRect.x + delta.x))
                            var newY = Math.max(0, Math.min(root.height - nodeRect.height, nodeRect.y + delta.y))
                            nodeModel.setProperty(index, "nodeX", newX)
                            nodeModel.setProperty(index, "nodeY", newY)
                            registerHotspots()
                            hotspotTimer.start()
                        }
                        onReleased: {
                            bridge.autoSave(getChatModelJson(), getNodeModelJson())
                        }
                    }
                }

                WebEngineView {
                    id: nodeWeb
                    anchors.top: nodeHeader.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    anchors.margins: 4
                    backgroundColor: "transparent"
                    zoomFactor: model.zoomScale
                    property string webContent: model.content
                    
                    function injectScrollbar(html) {
                        var scrollStyle = "<style>" +
                            "  ::-webkit-scrollbar { width: 6px; height: 6px; }" +
                            "  ::-webkit-scrollbar-track { background: rgba(15, 23, 42, 0.3); border-radius: 3px; }" +
                            "  ::-webkit-scrollbar-thumb { background: rgba(0, 242, 255, 0.45); border-radius: 3px; border: 1px solid rgba(0, 242, 255, 0.15); }" +
                            "  ::-webkit-scrollbar-thumb:hover { background: rgba(0, 242, 255, 0.85); box-shadow: 0 0 10px rgba(0, 242, 255, 0.6); }" +
                            "</style>";
                        if (html.indexOf("</head>") !== -1) {
                            return html.replace("</head>", scrollStyle + "</head>");
                        } else if (html.indexOf("</body>") !== -1) {
                            return html.replace("</body>", scrollStyle + "</body>");
                        } else {
                            return html + scrollStyle;
                        }
                    }

                    onWebContentChanged: {
                        loadHtml("")
                        loadHtml(injectScrollbar(webContent))
                    }
                    Component.onCompleted: { loadHtml(injectScrollbar(webContent)) }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════
    //  INIT — CINEMATIC BOOT SEQUENCE
    // ═══════════════════════════════════════════════

    Component.onCompleted: {
        loadStartupSettings()
        activeModels = JSON.parse(bridge.getActiveModels())
        bridge.shiftToActiveScreen()
        inputField.forceActiveFocus()
        registerHotspots()
        bootSequence.start()
        bridge.playSound("startup")
    }

    // Cinematic staggered boot sequence
    SequentialAnimation {
        id: bootSequence

        // Phase 1: Dock slides up (0ms)
        NumberAnimation { target: root; property: "bootPhase"; to: 1; duration: 0 }

        // Phase 2: Wait for dock to reach position (350ms)
        PauseAnimation { duration: 350 }

        // Phase 3: Reveal dock + first buttons
        ScriptAction { script: { isBooting = false } }
        PauseAnimation { duration: 100 }

        // Phase 4: Stagger button reveals
        PauseAnimation { duration: 80 }
        ScriptAction { script: { chatBtn.opacity = 1.0; chatBtn.scale = 1.0 } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { micBtn.opacity = 1.0; micBtn.scale = 1.0 } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { sendBtn.opacity = 1.0; sendBtn.scale = 1.0 } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { sidebarBtn.opacity = 1.0; sidebarBtn.scale = 1.0 } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { newChatBtn.opacity = 1.0; newChatBtn.scale = 1.0 } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { searchBtn.opacity = 1.0; searchBtn.scale = 1.0 } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { minBtn.opacity = 1.0; minBtn.scale = 1.0 } }

        // Phase 5: Avatar reveals with dramatic entrance
        PauseAnimation { duration: 200 }
        ScriptAction { script: { iraAvatar.opacity = root.avatarOpacity; iraAvatar.scale = 1.0; avatarGlowAnim.start() } }

        // Phase 6: Close button drops in
        PauseAnimation { duration: 150 }
        ScriptAction { script: { closeIrBtn.y = 5; closeIrBtn.opacity = 0.5; closeIrBtn.scale = 1.0 } }

        // Phase 7: Dock glow pulse
        PauseAnimation { duration: 100 }
        ScriptAction { script: { dockGlowAnim.start() } }
    }

    // Re-entry animation (when showing HUD after hide)
    onVisibleChanged: {
        if (visible && !isBooting) {
            // Reset to boot state for cinematic re-entry
            isBooting = true
            iraAvatar.scale = 0.3
            iraAvatar.opacity = 0
            closeIrBtn.y = -40
            closeIrBtn.opacity = 0
            closeIrBtn.scale = 0.5
            chatBtn.opacity = 0; chatBtn.scale = 0.3
            micBtn.opacity = 0; micBtn.scale = 0.3
            sendBtn.opacity = 0; sendBtn.scale = 0.3
            sidebarBtn.opacity = 0; sidebarBtn.scale = 0.3
            newChatBtn.opacity = 0; newChatBtn.scale = 0.3
            searchBtn.opacity = 0; searchBtn.scale = 0.3
            minBtn.opacity = 0; minBtn.scale = 0.3
            reentrySequence.start()
        }
    }

    SequentialAnimation {
        id: reentrySequence

        PauseAnimation { duration: 100 }
        ScriptAction { script: { isBooting = false } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { chatBtn.opacity = 1.0; chatBtn.scale = 1.0 } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: { micBtn.opacity = 1.0; micBtn.scale = 1.0 } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: { sendBtn.opacity = 1.0; sendBtn.scale = 1.0 } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: { sidebarBtn.opacity = 1.0; sidebarBtn.scale = 1.0 } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: { newChatBtn.opacity = 1.0; newChatBtn.scale = 1.0 } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: { searchBtn.opacity = 1.0; searchBtn.scale = 1.0 } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: { minBtn.opacity = 1.0; minBtn.scale = 1.0 } }
        PauseAnimation { duration: 150 }
        ScriptAction { script: { iraAvatar.opacity = root.avatarOpacity; iraAvatar.scale = 1.0; avatarGlowAnim.start() } }
        PauseAnimation { duration: 100 }
        ScriptAction { script: { closeIrBtn.y = 5; closeIrBtn.opacity = 0.5; closeIrBtn.scale = 1.0 } }
        PauseAnimation { duration: 80 }
        ScriptAction { script: { dockGlowAnim.start() } }
    }

    onWidthChanged: { registerHotspots(); hotspotTimer.start() }
    onHeightChanged: { registerHotspots(); hotspotTimer.start() }
}
