import { app } from "/scripts/app.js";

const TARGETS = new Set(["UmiBackgroundRemove", "UmiSegment"]);

function removePanel(node) {
    if (!node || !node.widgets) return;
    const panel = node.widgets.find(w => w.name === "UmiRmbgPanel");
    if (!panel) return;
    if (panel.element && panel.element.parentNode) {
        panel.element.parentNode.removeChild(panel.element);
    }
    node.widgets = node.widgets.filter(w => w !== panel);
    if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "UmiAI.RMBG.Cleanup",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!TARGETS.has(nodeData.name)) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);
            removePanel(this);
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            if (onConfigure) onConfigure.apply(this, arguments);
            removePanel(this);
        };
    }
});
