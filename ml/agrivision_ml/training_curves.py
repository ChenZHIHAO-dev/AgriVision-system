# 从逐轮指标生成 PNG。Agg 直接渲染文件，服务器或终端训练时可以后台画图。
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator, PercentFormatter


# 左图对照训练与验证损失，右图对照 Top-1 准确率。横轴使用实际完成的轮次。
def save_training_curves(history, output):
    figure = Figure(figsize=(10, 4), dpi=150, layout="constrained")
    canvas = FigureCanvasAgg(figure)
    loss_axis, accuracy_axis = figure.subplots(1, 2)
    epochs = [row["epoch"] for row in history]

    # 训练准确率记录为 train_accuracy，验证准确率沿用评估函数的 accuracy 字段。
    for axis, label, train_key, val_key in (
        (loss_axis, "Cross-entropy loss", "loss", "val_loss"),
        (accuracy_axis, "Top-1 accuracy", "train_accuracy", "accuracy"),
    ):
        for key, style, color, series in (
            (train_key, "o-", "#176456", "Train"),
            (val_key, "s--", "#a04a23", "Validation"),
        ):
            # 跳过缺失指标的轮次，例如本轮未读到可训练的完整批次时记录的 None。
            points = [(row["epoch"], row[key]) for row in history if row.get(key) is not None]
            if points:
                axis.plot(*zip(*points), style, color=color, label=series)
        axis.set(xlabel="Epoch", ylabel=label, xlim=(0.8, epochs[-1] + 0.2))
        axis.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True, min_n_ticks=1))
        axis.grid(axis="y", color="#e1e5e3", linewidth=0.8)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(frameon=False)

    # 准确率内部保存为 0 到 1 的比例，绘图时换成百分数显示。
    accuracy_axis.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    bottom, top = accuracy_axis.get_ylim()
    accuracy_axis.set_ylim(max(0, bottom), min(1, top))
    canvas.print_png(output)
