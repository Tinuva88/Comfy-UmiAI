import { app } from "/scripts/app.js";

app.registerExtension({
    name: "UmiAI.TextBypass",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "UmiTextBypass") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);
            const legacyMatchedWidget = this.widgets?.find(w => w.name === "matched");
            if (legacyMatchedWidget) {
                legacyMatchedWidget.type = "hidden";
                legacyMatchedWidget.hidden = true;
                legacyMatchedWidget.computeSize = () => [0, -4];
                this.setSize(this.computeSize());
            }
            const legacyMatchedInputIndex = this.inputs?.findIndex(i => i?.name === "matched");
            if (legacyMatchedInputIndex !== undefined && legacyMatchedInputIndex >= 0) {
                this.removeInput(legacyMatchedInputIndex);
                this.setSize(this.computeSize());
            }
        };
    }
});
