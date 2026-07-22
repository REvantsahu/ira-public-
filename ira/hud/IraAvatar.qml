import QtQuick 2.15

Item {
    id: root

    property string avatarState: "idle"
    property string avatarExpression: "normal"
    property real avatarOpacity: 1.0
    property int mouseX: 0
    property int mouseY: 0
    property string mainThemeColor: "#00F5FF"
    property string secThemeColor: "#9B59F5"

    onAvatarExpressionChanged: canvas.requestPaint()
    onMouseXChanged: canvas.requestPaint()
    onMouseYChanged: canvas.requestPaint()
    onMainThemeColorChanged: canvas.requestPaint()
    onSecThemeColorChanged: canvas.requestPaint()


    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: false
        renderStrategy: Canvas.Cooperative
        opacity: root.avatarOpacity
        Behavior on opacity { NumberAnimation { duration: 280 } }

        onPaint: {
            var ctx = getContext("2d")
            var w = width
            var h = height
            ctx.clearRect(0, 0, w, h)

            ctx.save()
            ctx.scale(w / 400, h / 400)
            ctx.translate(200, 200)

            var state = root.avatarState
            var expr = root.avatarExpression
            var fi = Math.floor((Date.now() / 33) % 30)
            var t = Date.now() / 33.0 // continuous time for smooth animations

            // Calculate mouse tracking offset (lookX, lookY)
            var scaleX = 400 / w
            var scaleY = 400 / h
            var localMouseX = root.mouseX - root.x
            var localMouseY = root.mouseY - root.y
            var canvasMouseX = localMouseX * scaleX
            var canvasMouseY = localMouseY * scaleY
            var dx = canvasMouseX - 200
            var dy = canvasMouseY - 200
            var dist = Math.sqrt(dx * dx + dy * dy)
            var maxLook = 6
            var lookX = 0
            var lookY = 0
            if (dist > 0) {
                var factor = Math.min(maxLook, dist * 0.05) / dist
                lookX = dx * factor
                lookY = dy * factor
            }
            
            var mainColor = root.mainThemeColor
            var secColor = root.secThemeColor
            var earColor = root.secThemeColor
            var mouthColor = root.mainThemeColor
            var lineColor = root.mainThemeColor
            
            if (expr === "angry") {
                mainColor = "#FF3333"
                secColor = "#FF5555"
                earColor = "#FF3333"
                mouthColor = "#FF3333"
                lineColor = "#FF3333"
            } else if (state === "listening")      { earColor = "#00FF88"; mouthColor = "#00FF88"; lineColor = "#00FF88"; secColor = root.mainThemeColor }
            else if (state === "thinking")  { earColor = "#FFB347"; mouthColor = "#FFB347"; lineColor = "#FFB347"; secColor = root.mainThemeColor }
            else if (state === "talking")   { earColor = root.secThemeColor; mouthColor = "#00FF88"; lineColor = root.secThemeColor; secColor = root.mainThemeColor }

            var bob = Math.sin((fi * Math.PI) / 15) * 2.5
            var headY = 0
            var earAngle = 0
            var eyeOffset = 0
            var eyesBlink = false
            var mouthOpen = false
            var mouthH = 2
            var mouthSmile = false
            var mouthFrown = false
            var browsRaise = false
            var headShakeX = 0

            if (state === "idle") {
                if (fi % 30 === 12 || fi % 30 === 13 || fi % 30 === 25 || fi % 30 === 26) eyesBlink = true
                headY = bob * 0.4
            } else if (state === "listening") {
                headY = 3 + Math.sin((fi * Math.PI) / 15) * 1.2
                earAngle = -3
            } else if (state === "thinking") {
                eyeOffset = Math.sin((fi * Math.PI) / 15) * 4
                headY = Math.sin((fi * Math.PI) / 15) * 0.8
            } else if (state === "talking") {
                var speechFreqs = [0.1, 0.4, 0.9, 0.3, 0.7, 0.2, 0.8, 0.5]
                var sf = speechFreqs[fi % speechFreqs.length]
                mouthH = 4 + sf * 16
                mouthOpen = true
                headY = bob * 0.6
                earAngle = Math.sin((fi * Math.PI) / 5) * 1.5
            }

            // ── GESTURE MIRRORING — overlay user's face/hands onto avatar ──
            if (root.userBlinking) eyesBlink = true
            if (root.userMouthOpen && !mouthOpen) { mouthOpen = true; mouthH = 10 }
            if (root.userSmiling) mouthSmile = true
            if (root.userFrowning) mouthFrown = true
            if (root.userBrowsRaised) browsRaise = true
            if (root.userHeadNod) headY += Math.sin((fi * Math.PI) / 8) * 3
            if (root.userHeadShake) headShakeX = Math.sin((fi * Math.PI) / 6) * 4

            var scanRot = (t * 8) % 360
            if (state === "thinking") {
                scanRot = (t * 18) % 360 // faster rotation during thinking
            }

            // ── RADAR RINGS (simplified — no gradient) ──
            var pulseRadius = 160
            if (state === "thinking") {
                pulseRadius = 160 + Math.sin(t * 0.3) * 8
            }
            ctx.beginPath()
            ctx.arc(0, 0, pulseRadius, 0, Math.PI * 2)
            ctx.fillStyle = hexToRgba(mainColor, state === "thinking" ? 0.07 : 0.04)
            ctx.fill()

            ctx.beginPath()
            ctx.arc(0, 0, 150, 0, Math.PI * 2)
            ctx.strokeStyle = hexToRgba(lineColor, 0.06)
            ctx.lineWidth = 1.5
            ctx.stroke()

            // Scanner rings (single ring, no save/restore)
            ctx.save()
            ctx.rotate(scanRot * Math.PI / 180)
            ctx.beginPath()
            ctx.arc(0, 0, 175, 0, Math.PI * 2)
            ctx.setLineDash([40, 110])
            ctx.strokeStyle = hexToRgba(mainColor, 0.1)
            ctx.lineWidth = 1.5
            ctx.stroke()
            ctx.restore()
            ctx.setLineDash([])

            // ── HUD CROSSHAIRS ──
            ctx.strokeStyle = hexToRgba(mainColor, 0.15)
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(0, -190); ctx.lineTo(0, -175)
            ctx.moveTo(0, 175);  ctx.lineTo(0, 190)
            ctx.moveTo(-190, 0); ctx.lineTo(-175, 0)
            ctx.moveTo(175, 0);  ctx.lineTo(190, 0)
            ctx.stroke()

            // ── COLLAR & SHOULDERS ──
            ctx.save()
            ctx.translate(0, headY * 0.5)
            ctx.beginPath()
            ctx.moveTo(-80, 140)
            ctx.bezierCurveTo(-60, 110, 60, 110, 80, 140)
            ctx.lineTo(100, 190)
            ctx.lineTo(-100, 190)
            ctx.closePath()
            ctx.strokeStyle = hexToRgba(mainColor, 0.25)
            ctx.lineWidth = 2
            ctx.stroke()

            // Dashed collar line (batched)
            ctx.beginPath()
            ctx.moveTo(-60, 135)
            ctx.lineTo(60, 135)
            ctx.strokeStyle = hexToRgba(lineColor, 0.35)
            ctx.lineWidth = 1
            ctx.setLineDash([5, 5])
            ctx.stroke()
            ctx.setLineDash([])

            // Vertical connectors (batched)
            ctx.beginPath()
            ctx.moveTo(-25, 100); ctx.lineTo(-25, 130)
            ctx.moveTo(25, 100);  ctx.lineTo(25, 130)
            ctx.strokeStyle = hexToRgba(mainColor, 0.35)
            ctx.lineWidth = 1
            ctx.stroke()

            // Neck cylinders (batched)
            ctx.beginPath()
            ctx.moveTo(-22, 75)
            ctx.lineTo(-22, 110)
            ctx.bezierCurveTo(-22, 112, 22, 112, 22, 110)
            ctx.lineTo(22, 75)
            ctx.closePath()
            ctx.strokeStyle = hexToRgba(mainColor, 0.35)
            ctx.lineWidth = 2
            ctx.stroke()

            ctx.fillStyle = hexToRgba(lineColor, 0.5)
            ctx.fillRect(-8, 85, 16, 4)
            ctx.fillRect(-8, 95, 16, 4)

            // --- PROCEDURAL ROBOTIC ARMS AND GESTURES ---
            if (expr === "giggling") {
                // Right arm covering mouth
                var mouthX_in_shoulder = headShakeX
                var mouthY_in_shoulder = headY * 0.5 + 25
                
                ctx.save()
                ctx.strokeStyle = mainColor
                ctx.fillStyle = "#060810"
                ctx.lineWidth = 3
                // Shoulder joint circle
                ctx.beginPath()
                ctx.arc(80, 140, 6, 0, Math.PI * 2)
                ctx.fill(); ctx.stroke()
                // Arm path (Shoulder -> Elbow -> Hand covering mouth)
                var elbowX = 100, elbowY = 85
                ctx.beginPath()
                ctx.moveTo(80, 140)
                ctx.lineTo(elbowX, elbowY)
                ctx.lineTo(mouthX_in_shoulder, mouthY_in_shoulder)
                ctx.stroke()
                // Elbow joint circle
                ctx.beginPath()
                ctx.arc(elbowX, elbowY, 4, 0, Math.PI * 2)
                ctx.fillStyle = secColor
                ctx.fill(); ctx.stroke()
                // Hand covering mouth
                ctx.beginPath()
                ctx.arc(mouthX_in_shoulder, mouthY_in_shoulder, 8, 0, Math.PI * 2)
                ctx.fillStyle = hexToRgba(lineColor, 0.95)
                ctx.fill(); ctx.stroke()
                ctx.restore()
            } else if (expr === "facepalm") {
                // Right arm hitting forehead
                var foreheadX_in_shoulder = headShakeX
                var foreheadY_in_shoulder = headY * 0.5 - 20
                
                ctx.save()
                ctx.strokeStyle = mainColor
                ctx.fillStyle = "#060810"
                ctx.lineWidth = 3
                // Shoulder joint circle
                ctx.beginPath()
                ctx.arc(80, 140, 6, 0, Math.PI * 2)
                ctx.fill(); ctx.stroke()
                // Arm path (Shoulder -> Elbow -> Hand hitting forehead)
                var elbowX = 110, elbowY = 75
                ctx.beginPath()
                ctx.moveTo(80, 140)
                ctx.lineTo(elbowX, elbowY)
                ctx.lineTo(foreheadX_in_shoulder, foreheadY_in_shoulder)
                ctx.stroke()
                // Elbow joint circle
                ctx.beginPath()
                ctx.arc(elbowX, elbowY, 4, 0, Math.PI * 2)
                ctx.fillStyle = secColor
                ctx.fill(); ctx.stroke()
                // Hand hitting forehead
                ctx.beginPath()
                ctx.arc(foreheadX_in_shoulder, foreheadY_in_shoulder, 10, 0, Math.PI * 2)
                ctx.fillStyle = hexToRgba(lineColor, 0.95)
                ctx.fill(); ctx.stroke()
                // Yellow impact star
                ctx.strokeStyle = "#FFFF33"
                ctx.lineWidth = 1.5
                var sx = foreheadX_in_shoulder - 18, sy = foreheadY_in_shoulder - 10
                ctx.beginPath()
                ctx.moveTo(sx, sy - 5); ctx.lineTo(sx, sy + 5)
                ctx.moveTo(sx - 5, sy); ctx.lineTo(sx + 5, sy)
                ctx.stroke()
                ctx.restore()
            } else if (expr === "happy" || expr === "shocked") {
                // Shrugging raised hands (both sides)
                ctx.save()
                ctx.strokeStyle = mainColor
                ctx.fillStyle = "#060810"
                ctx.lineWidth = 3
                
                // Left arm
                ctx.beginPath()
                ctx.arc(-80, 140, 6, 0, Math.PI * 2)
                ctx.fill(); ctx.stroke()
                ctx.beginPath()
                ctx.moveTo(-80, 140)
                ctx.lineTo(-105, 110)
                ctx.lineTo(-85, 80)
                ctx.stroke()
                ctx.beginPath()
                ctx.arc(-105, 110, 4, 0, Math.PI * 2)
                ctx.fillStyle = secColor
                ctx.fill(); ctx.stroke()
                ctx.beginPath()
                ctx.arc(-85, 80, 6, 0, Math.PI * 2)
                ctx.fillStyle = hexToRgba(lineColor, 0.95)
                ctx.fill(); ctx.stroke()
                
                // Right arm
                ctx.beginPath()
                ctx.arc(80, 140, 6, 0, Math.PI * 2)
                ctx.fillStyle = "#060810"
                ctx.fill(); ctx.stroke()
                ctx.beginPath()
                ctx.moveTo(80, 140)
                ctx.lineTo(105, 110)
                ctx.lineTo(85, 80)
                ctx.stroke()
                ctx.beginPath()
                ctx.arc(105, 110, 4, 0, Math.PI * 2)
                ctx.fillStyle = secColor
                ctx.fill(); ctx.stroke()
                ctx.beginPath()
                ctx.arc(85, 80, 6, 0, Math.PI * 2)
                ctx.fillStyle = hexToRgba(lineColor, 0.95)
                ctx.fill(); ctx.stroke()
                
                ctx.restore()
            }

            ctx.restore()

            // ── HEAD ──
            ctx.save()
            ctx.translate(headShakeX, headY)

            // LEFT EAR
            ctx.save()
            ctx.translate(-55, -80)
            ctx.rotate((-15 + earAngle) * Math.PI / 180)
            ctx.beginPath()
            ctx.moveTo(-5, 10)
            ctx.lineTo(-45, -35)
            ctx.lineTo(15, -10)
            ctx.closePath()
            ctx.strokeStyle = earColor
            ctx.lineWidth = 2.5
            ctx.fillStyle = "#060810"
            ctx.fill()
            ctx.stroke()
            // Inner ear
            ctx.beginPath()
            ctx.moveTo(-2, 5)
            ctx.lineTo(-25, -15)
            ctx.lineTo(5, -5)
            ctx.closePath()
            ctx.strokeStyle = hexToRgba(secColor, 0.7)
            ctx.lineWidth = 1.5
            ctx.stroke()
            ctx.restore()

            // RIGHT EAR
            ctx.save()
            ctx.translate(55, -80)
            ctx.rotate((15 - earAngle) * Math.PI / 180)
            ctx.beginPath()
            ctx.moveTo(5, 10)
            ctx.lineTo(45, -35)
            ctx.lineTo(-15, -10)
            ctx.closePath()
            ctx.strokeStyle = earColor
            ctx.lineWidth = 2.5
            ctx.fillStyle = "#060810"
            ctx.fill()
            ctx.stroke()
            // Inner ear
            ctx.beginPath()
            ctx.moveTo(2, 5)
            ctx.lineTo(25, -15)
            ctx.lineTo(-5, -5)
            ctx.closePath()
            ctx.strokeStyle = hexToRgba(secColor, 0.7)
            ctx.lineWidth = 1.5
            ctx.stroke()
            ctx.restore()

            // HEAD SHIELD
            ctx.beginPath()
            ctx.moveTo(-70, -20)
            ctx.bezierCurveTo(-70, 60, 70, 60, 70, -20)
            ctx.bezierCurveTo(70, -50, -70, -50, -70, -20)
            ctx.closePath()
            ctx.strokeStyle = mainColor
            ctx.lineWidth = 2.5
            ctx.fillStyle = "#060810"
            ctx.fill()
            ctx.stroke()

            // FACIAL PANEL LINES (batched)
            ctx.beginPath()
            ctx.moveTo(-66, 0); ctx.lineTo(-45, 10); ctx.lineTo(-45, 35)
            ctx.moveTo(66, 0);  ctx.lineTo(45, 10);  ctx.lineTo(45, 35)
            ctx.moveTo(0, 45);  ctx.lineTo(0, 60)
            ctx.strokeStyle = hexToRgba(lineColor, 0.25)
            ctx.lineWidth = 1.5
            ctx.stroke()

            // SIDE MOUNTS (batched)
            ctx.fillStyle = "#060810"
            ctx.strokeStyle = mainColor
            ctx.lineWidth = 2
            roundRect(ctx, -85, -45, 16, 40, 4)
            ctx.fill(); ctx.stroke()
            roundRect(ctx, 69, -45, 16, 40, 4)
            ctx.fill(); ctx.stroke()

            // Side mount dots (no shadow — just bright fill)
            ctx.fillStyle = lineColor
            ctx.beginPath()
            ctx.arc(-77, -25, 3, 0, Math.PI * 2)
            ctx.fill()
            ctx.beginPath()
            ctx.arc(77, -25, 3, 0, Math.PI * 2)
            ctx.fill()

            // HAIR PANELS (batched)
            ctx.beginPath()
            ctx.moveTo(-65, -50)
            ctx.lineTo(-50, -25)
            ctx.lineTo(-40, -40)
            ctx.lineTo(-20, -15)
            ctx.lineTo(0, -40)
            ctx.lineTo(20, -15)
            ctx.lineTo(40, -40)
            ctx.lineTo(50, -25)
            ctx.lineTo(65, -50)
            ctx.moveTo(-75, -30)
            ctx.lineTo(-65, 40)
            ctx.lineTo(-55, 10)
            ctx.moveTo(75, -30)
            ctx.lineTo(65, 40)
            ctx.lineTo(55, 10)
            ctx.strokeStyle = lineColor
            ctx.lineWidth = 2
            ctx.stroke()

            // LEFT EYE
            ctx.save()
            ctx.translate(-30, -15)
            // Brow
            ctx.beginPath()
            ctx.moveTo(-22, -2)
            ctx.bezierCurveTo(-18, -12, 10, -12, 14, -2)
            ctx.strokeStyle = mainColor
            ctx.lineWidth = 3
            ctx.stroke()
            // Under line
            ctx.beginPath()
            ctx.moveTo(-18, 4); ctx.lineTo(10, 4)
            ctx.strokeStyle = hexToRgba(mainColor, 0.5)
            ctx.lineWidth = 1
            ctx.stroke()

            ctx.save() // shift eye towards cursor
            ctx.translate(lookX, lookY)

            if (eyesBlink) {
                ctx.beginPath()
                ctx.moveTo(-18, -4); ctx.lineTo(10, -4)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 3
                ctx.stroke()
            } else if (expr === "giggling" || expr === "happy" || expr === "blushing") {
                // Closed smiling eye ^
                ctx.beginPath()
                ctx.moveTo(-18, 2)
                ctx.bezierCurveTo(-12, -6, 5, -6, 10, 2)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 3.5
                ctx.stroke()
            } else if (expr === "shocked") {
                // Wide open eye
                ctx.beginPath()
                ctx.ellipse(eyeOffset, -3, 15, 15, 0, 0, Math.PI * 2)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 2.5
                ctx.stroke()
                
                // Tiny pupil
                ctx.fillStyle = "#FFFFFF"
                ctx.beginPath()
                ctx.arc(eyeOffset, -3, 1.5, 0, Math.PI * 2)
                ctx.fill()
            } else if (expr === "smirking") {
                // Half-closed smug eye
                ctx.beginPath()
                ctx.ellipse(eyeOffset, 0, 10, 5, 0, 0, Math.PI * 2)
                ctx.strokeStyle = secColor
                ctx.lineWidth = 2
                ctx.stroke()
                
                // Pupil
                ctx.fillStyle = "#FFFFFF"
                ctx.beginPath()
                ctx.arc(eyeOffset + 1, -1, 1.8, 0, Math.PI * 2)
                ctx.fill()
            } else {
                // Iris
                ctx.beginPath()
                ctx.ellipse(eyeOffset, -3, 10, 12, 0, 0, Math.PI * 2)
                ctx.strokeStyle = secColor
                ctx.lineWidth = 2
                ctx.stroke()

                // Thinking spinning rings overlay
                if (state === "thinking") {
                    ctx.save()
                    ctx.translate(eyeOffset, -3)
                    ctx.rotate((t * 22 * Math.PI) / 180)
                    ctx.beginPath()
                    ctx.arc(0, 0, 14, 0, Math.PI * 1.5)
                    ctx.strokeStyle = mainColor
                    ctx.lineWidth = 1.5
                    ctx.stroke()
                    ctx.restore()
                }

                // Pupil
                ctx.fillStyle = "#FFFFFF"
                ctx.beginPath()
                ctx.arc(eyeOffset + 2, -5, 2.5, 0, Math.PI * 2)
                ctx.fill()
                // Scan line
                ctx.beginPath()
                ctx.moveTo(eyeOffset - 6, -3); ctx.lineTo(eyeOffset + 6, -3)
                ctx.strokeStyle = hexToRgba(mainColor, 0.6)
                ctx.lineWidth = 1
                ctx.stroke()
            }
            ctx.restore() // restore eye shift
            ctx.restore() // restore eye translate

            // RIGHT EYE
            ctx.save()
            ctx.translate(30, -15)
            ctx.beginPath()
            ctx.moveTo(-14, -2)
            ctx.bezierCurveTo(-10, -12, 18, -12, 22, -2)
            ctx.strokeStyle = mainColor
            ctx.lineWidth = 3
            ctx.stroke()
            ctx.beginPath()
            ctx.moveTo(-10, 4); ctx.lineTo(18, 4)
            ctx.strokeStyle = hexToRgba(mainColor, 0.5)
            ctx.lineWidth = 1
            ctx.stroke()

            ctx.save() // shift eye towards cursor
            ctx.translate(lookX, lookY)

            if (eyesBlink) {
                ctx.beginPath()
                ctx.moveTo(-10, -4); ctx.lineTo(18, -4)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 3
                ctx.stroke()
            } else if (expr === "giggling" || expr === "happy" || expr === "blushing") {
                // Closed smiling eye ^
                ctx.beginPath()
                ctx.moveTo(-10, 2)
                ctx.bezierCurveTo(-5, -6, 12, -6, 18, 2)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 3.5
                ctx.stroke()
            } else if (expr === "shocked") {
                // Wide open eye
                ctx.beginPath()
                ctx.ellipse(eyeOffset, -3, 15, 15, 0, 0, Math.PI * 2)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 2.5
                ctx.stroke()
                
                // Tiny pupil
                ctx.fillStyle = "#FFFFFF"
                ctx.beginPath()
                ctx.arc(eyeOffset, -3, 1.5, 0, Math.PI * 2)
                ctx.fill()
            } else if (expr === "smirking") {
                // Half-closed smug eye
                ctx.beginPath()
                ctx.ellipse(eyeOffset, 0, 10, 5, 0, 0, Math.PI * 2)
                ctx.strokeStyle = secColor
                ctx.lineWidth = 2
                ctx.stroke()
                
                // Pupil
                ctx.fillStyle = "#FFFFFF"
                ctx.beginPath()
                ctx.arc(eyeOffset + 1, -1, 1.8, 0, Math.PI * 2)
                ctx.fill()
            } else {
                ctx.beginPath()
                ctx.ellipse(eyeOffset, -3, 10, 12, 0, 0, Math.PI * 2)
                ctx.strokeStyle = secColor
                ctx.lineWidth = 2
                ctx.stroke()

                // Thinking spinning rings overlay
                if (state === "thinking") {
                    ctx.save()
                    ctx.translate(eyeOffset, -3)
                    ctx.rotate((-t * 22 * Math.PI) / 180) // spins counter-clockwise for asymmetry
                    ctx.beginPath()
                    ctx.arc(0, 0, 14, 0, Math.PI * 1.5)
                    ctx.strokeStyle = mainColor
                    ctx.lineWidth = 1.5
                    ctx.stroke()
                    ctx.restore()
                }

                ctx.fillStyle = "#FFFFFF"
                ctx.beginPath()
                ctx.arc(eyeOffset + 2, -5, 2.5, 0, Math.PI * 2)
                ctx.fill()
                ctx.beginPath()
                ctx.moveTo(eyeOffset - 6, -3); ctx.lineTo(eyeOffset + 6, -3)
                ctx.strokeStyle = hexToRgba(mainColor, 0.6)
                ctx.lineWidth = 1
                ctx.stroke()
            }
            ctx.restore() // restore eye shift
            ctx.restore() // restore eye translate

            // CHEEK HUD LINES (batched)
            ctx.beginPath()
            ctx.moveTo(-55, 2); ctx.lineTo(-49, -3)
            ctx.moveTo(-49, 2); ctx.lineTo(-43, -3)
            ctx.moveTo(43, 2);  ctx.lineTo(49, -3)
            ctx.moveTo(49, 2);  ctx.lineTo(55, -3)
            ctx.strokeStyle = hexToRgba(lineColor, 0.25)
            ctx.lineWidth = 1
            ctx.stroke()

            // Glowing pink blush cheeks
            if (expr === "blushing" || expr === "giggling" || expr === "happy") {
                ctx.save()
                ctx.fillStyle = "rgba(255, 105, 180, 0.45)"
                ctx.beginPath()
                ctx.ellipse(-48, 5, 12, 6, 10 * Math.PI / 180, 0, Math.PI * 2)
                ctx.fill()
                ctx.beginPath()
                ctx.ellipse(48, 5, 12, 6, -10 * Math.PI / 180, 0, Math.PI * 2)
                ctx.fill()
                ctx.restore()
            }

            // EYEBROWS (batched) — raise when user raises brows
            var browY = browsRaise ? -35 : (state === "thinking" ? -28 : -30)
            
            if (expr === "angry") {
                ctx.beginPath()
                ctx.moveTo(-48, -34); ctx.lineTo(-22, -24)
                ctx.moveTo(48, -34);  ctx.lineTo(22, -24)
                ctx.strokeStyle = "#FF3333"
                ctx.lineWidth = 3
                ctx.stroke()
            } else if (expr === "sad" || expr === "facepalm") {
                ctx.beginPath()
                ctx.moveTo(-48, -24); ctx.lineTo(-22, -34)
                ctx.moveTo(48, -24);  ctx.lineTo(22, -34)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            } else if (expr === "shocked") {
                ctx.beginPath()
                ctx.moveTo(-48, -38); ctx.bezierCurveTo(-42, -43, -22, -40, -22, -37)
                ctx.moveTo(48, -38);  ctx.bezierCurveTo(42, -43, 22, -40, 22, -37)
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 2
                ctx.stroke()
            } else {
                ctx.beginPath()
                if (state === "thinking") {
                    ctx.moveTo(-48, browY - 2)
                    ctx.lineTo(-22, browY + 3)
                    ctx.moveTo(48, browY - 2)
                    ctx.lineTo(22, browY + 3)
                } else {
                    ctx.moveTo(-48, browY)
                    ctx.bezierCurveTo(-42, browY - 5, -22, browY - 2, -22, browY + 1)
                    ctx.moveTo(48, browY)
                    ctx.bezierCurveTo(42, browY - 5, 22, browY - 2, 22, browY + 1)
                }
                ctx.strokeStyle = mainColor
                ctx.lineWidth = 1.5
                ctx.stroke()
            }

            // FLOATING COMPUTING PARTICLES (glowing data nodes) in Thinking state
            if (state === "thinking") {
                ctx.save()
                ctx.strokeStyle = hexToRgba(mainColor, 0.4)
                ctx.fillStyle = hexToRgba(mainColor, 0.4)
                ctx.lineWidth = 1
                for (var p = 0; p < 4; p++) {
                    var angle = ((t * 2 + p * 90) % 360) * Math.PI / 180
                    var radius = 100 + Math.sin(t * 0.15 + p) * 10
                    var px = Math.cos(angle) * radius
                    var py = Math.sin(angle) * radius - 20
                    
                    // Draw node dot
                    ctx.beginPath()
                    ctx.arc(px, py, 2, 0, Math.PI * 2)
                    ctx.fill()
                    
                    // Draw connecting line from head edge to particle
                    ctx.beginPath()
                    ctx.moveTo(px * 0.7, py * 0.7)
                    ctx.lineTo(px, py)
                    ctx.strokeStyle = hexToRgba(mainColor, 0.15)
                    ctx.stroke()
                    
                    // Draw tiny '+' sign next to it
                    ctx.strokeStyle = hexToRgba(mainColor, 0.3)
                    ctx.beginPath()
                    ctx.moveTo(px + 4, py); ctx.lineTo(px + 8, py)
                    ctx.moveTo(px + 6, py - 2); ctx.lineTo(px + 6, py + 2)
                    ctx.stroke()
                }
                ctx.restore()
            }

            // NOSE
            ctx.beginPath()
            ctx.moveTo(-3, 5)
            ctx.lineTo(0, 9)
            ctx.lineTo(1, 9)
            ctx.strokeStyle = mainColor
            ctx.lineWidth = 1.5
            ctx.stroke()

            // MOUTH
            if (mouthOpen) {
                if (expr === "happy" || expr === "giggling" || expr === "blushing") {
                    // Wide laughing/smiling open mouth
                    ctx.beginPath()
                    ctx.moveTo(-12, 20)
                    ctx.bezierCurveTo(-12, 20, -10, 20 + mouthH, 0, 20 + mouthH)
                    ctx.bezierCurveTo(10, 20 + mouthH, 12, 20, 12, 20)
                    ctx.quadraticCurveTo(0, 23, -12, 20)
                    ctx.closePath()
                    ctx.fillStyle = hexToRgba(mouthColor, 0.2)
                    ctx.fill()
                    ctx.strokeStyle = mouthColor
                    ctx.lineWidth = 2.5
                    ctx.stroke()
                } else {
                    // Standard talking oval
                    ctx.beginPath()
                    ctx.moveTo(-10, 22)
                    ctx.bezierCurveTo(-10, 22, -12, 25 + mouthH / 2, 0, 25 + mouthH / 2)
                    ctx.bezierCurveTo(12, 25 + mouthH / 2, 10, 22, 10, 22)
                    ctx.bezierCurveTo(8, 20, -8, 20, -10, 22)
                    ctx.closePath()
                    ctx.strokeStyle = mouthColor
                    ctx.lineWidth = 2.5
                    ctx.stroke()
                }
                // Side lines
                ctx.beginPath()
                ctx.moveTo(-14, 25); ctx.lineTo(-8, 25)
                ctx.moveTo(8, 25);   ctx.lineTo(14, 25)
                ctx.strokeStyle = hexToRgba(secColor, 0.7)
                ctx.lineWidth = 1.5
                ctx.stroke()
            } else if (expr === "happy" || expr === "blushing" || expr === "giggling") {
                // Large C smile mouth
                ctx.beginPath()
                ctx.moveTo(-12, 22)
                ctx.quadraticCurveTo(0, 36, 12, 22)
                ctx.strokeStyle = mouthColor
                ctx.lineWidth = 3
                ctx.stroke()
            } else if (expr === "sad" || expr === "angry" || expr === "facepalm") {
                // Inverted C frown
                ctx.beginPath()
                ctx.moveTo(-8, 27)
                ctx.quadraticCurveTo(0, 21, 8, 27)
                ctx.strokeStyle = mouthColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            } else if (expr === "smirking") {
                // Asymmetric smirk mouth
                ctx.beginPath()
                ctx.moveTo(-8, 24)
                ctx.quadraticCurveTo(0, 27, 8, 19)
                ctx.strokeStyle = mouthColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            } else if (expr === "shocked") {
                // Wide open shocked O shape
                ctx.beginPath()
                ctx.ellipse(0, 26, 6, 12, 0, 0, Math.PI * 2)
                ctx.strokeStyle = mouthColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            } else if (mouthFrown) {
                ctx.beginPath()
                ctx.moveTo(-7, 26)
                ctx.quadraticCurveTo(0, 22, 7, 26)
                ctx.strokeStyle = mouthColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            } else if (mouthSmile || state === "listening" || state === "idle" || state === "thinking") {
                ctx.beginPath()
                ctx.moveTo(-7, 25)
                ctx.quadraticCurveTo(0, 30, 7, 25)
                ctx.strokeStyle = mouthColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            } else {
                ctx.beginPath()
                ctx.moveTo(-7, 25)
                ctx.lineTo(7, 25)
                ctx.strokeStyle = mouthColor
                ctx.lineWidth = 2.5
                ctx.stroke()
            }

            // Floating red anger cross symbol for angry expression
            if (expr === "angry") {
                ctx.save()
                ctx.strokeStyle = "#FF3333"
                ctx.lineWidth = 3
                ctx.lineCap = "round"
                var ax = 55, ay = -55
                ctx.beginPath()
                ctx.moveTo(ax - 8, ay - 8); ctx.quadraticCurveTo(ax, ay - 8, ax, ay - 16)
                ctx.moveTo(ax + 8, ay - 8); ctx.quadraticCurveTo(ax, ay - 8, ax, ay - 16)
                ctx.moveTo(ax - 8, ay + 8); ctx.quadraticCurveTo(ax, ay + 8, ax, ay + 16)
                ctx.moveTo(ax + 8, ay + 8); ctx.quadraticCurveTo(ax, ay + 8, ax, ay + 16)
                
                ctx.moveTo(ax - 8, ay - 8); ctx.quadraticCurveTo(ax - 8, ay, ax - 16, ay)
                ctx.moveTo(ax - 8, ay + 8); ctx.quadraticCurveTo(ax - 8, ay, ax - 16, ay)
                ctx.moveTo(ax + 8, ay - 8); ctx.quadraticCurveTo(ax + 8, ay, ax + 16, ay)
                ctx.moveTo(ax + 8, ay + 8); ctx.quadraticCurveTo(ax + 8, ay, ax + 16, ay)
                ctx.stroke()
                ctx.restore()
            }

            ctx.restore() // head transform
            ctx.restore() // center translate
            ctx.restore() // scale
        }
    }

    Timer {
        interval: 33
        running: true
        repeat: true
        onTriggered: canvas.requestPaint()
    }

    function hexToRgba(hex, a) {
        var h = hex.replace("#", "")
        var r = parseInt(h.substring(0, 2), 16)
        var g = parseInt(h.substring(2, 4), 16)
        var b = parseInt(h.substring(4, 6), 16)
        return "rgba(" + r + "," + g + "," + b + "," + a + ")"
    }

    function roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath()
        ctx.moveTo(x + r, y)
        ctx.lineTo(x + w - r, y)
        ctx.quadraticCurveTo(x + w, y, x + w, y + r)
        ctx.lineTo(x + w, y + h - r)
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
        ctx.lineTo(x + r, y + h)
        ctx.quadraticCurveTo(x, y + h, x, y + h - r)
        ctx.lineTo(x, y + r)
        ctx.quadraticCurveTo(x, y, x + r, y)
        ctx.closePath()
    }
}
