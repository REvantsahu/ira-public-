import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls 2.15

Rectangle {
    id: panelRoot

    property string panelTitle: "Panel"
    property bool expanded: false
    property color panelColor: Qt.rgba(13/255, 27/255, 58/255, 0.35)

    default property alias contentData: contentItem.data

    radius: 16
    color: panelColor
    border { color: Qt.rgba(78/255, 163/255, 255/255, 0.2); width: 1 }
    clip: true

    Rectangle {
        id: header
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: 0
        color: "transparent"
        z: 2
    }

    Item {
        id: contentItem
        anchors { top: header.bottom; left: parent.left; right: parent.right; bottom: parent.bottom }
        opacity: expanded ? 1.0 : 0.0
        visible: opacity > 0

        Behavior on opacity {
            NumberAnimation { duration: 150; easing.type: Easing.InOutQuad }
        }
    }

    // Collapse/expand overlay button
    Rectangle {
        anchors { top: parent.top; right: parent.right; topMargin: 6; rightMargin: 6 }
        width: 22; height: 22; radius: 11
        color: mouseCollapse.containsMouse ? Qt.rgba(78/255, 163/255, 255/255, 0.3) : Qt.rgba(0,0,0,0.3)
        border.color: Qt.rgba(78/255, 163/255, 255/255, 0.4)
        border.width: 1
        Text {
            anchors.centerIn: parent
            text: expanded ? "◀" : "▶"
            color: "#69C0FF"
            font.pixelSize: 10
        }
        MouseArea {
            id: mouseCollapse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: expanded = !expanded
        }
    }
}
