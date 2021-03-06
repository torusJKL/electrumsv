from typing import Optional

from PyQt5.QtCore import (QAbstractItemModel, Qt, QSize, QSortFilterProxyModel, QVariant,
    QModelIndex, pyqtSignal, QEvent, QObject)
from PyQt5.QtGui import QPainter, QPixmap, QPalette, QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import (QAction, QComboBox, QCompleter, QDialog, QDialogButtonBox,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
    QSizePolicy, QStyledItemDelegate, QTabWidget, QVBoxLayout, QWidget, QLayout,
    QStyleOptionViewItem, QStyle, QStyleOption, QTableView, QAbstractItemView)

from electrumsv.app_state import app_state
from electrumsv.i18n import _

from .util import icon_path, read_QIcon


# TODO: Handle case where there are no contacts.
#       - ...
# TODO: XXX


payee_badge_css = """
    #PayeeBadgeName, #PayeeBadgeSystem {
        color: white;
        font-weight: 400;
        border-width: 1px;
        border-style: solid;
        padding-left: 4px;
        padding-right: 4px;
        padding-top: 2px;
        padding-bottom: 2px;
    }

    #PayeeBadgeName {
        border: 1px solid #5A5A5A;
        background-color: #5A5A5A;
        border-top-left-radius: 2px;
        border-bottom-left-radius: 2px;
    }

    #PayeeBadgeName::menu-indicator {
        width: 0px;
        image: none;
    }

    #PayeeBadgeSystem {
        border: 1px solid #4AC41C;
        background-color: #4AC41C;
        border-top-right-radius: 2px;
        border-bottom-right-radius: 2px;
    }

    #PayeeBadgeName:focus, #PayeeBadgeSystem:focus {
        border: 1px solid black;
        background-color: white;
        color: black;
    }

    #PayeeBadgeName:hover, #PayeeBadgeSystem:hover {
        border: 1px solid black;
        background-color: grey;
        color: white;
    }
"""


class PaymentAmountWidget(QWidget):
    def __init__(self, local_api, parent=None):
        super().__init__(parent)
        self._local_api = local_api

        self.setObjectName("PaymentAmount")

        amount_widget = QLineEdit()
        currency_widget = QLineEdit()

        currency_combo = QComboBox()
        currency_combo.setEditable(True)

        filter_model = QSortFilterProxyModel(currency_combo)
        filter_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        filter_model.setSourceModel(currency_combo.model())

        contact_completer = QCompleter(filter_model, currency_combo)
        contact_completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        currency_combo.setCompleter(contact_completer)

        # base unit.
        # selected fiat currency.

        options = []
        base_unit = local_api.get_base_unit()
        options.append(base_unit)
        fiat_unit = local_api.get_fiat_unit()
        if fiat_unit is not None:
            options.append(fiat_unit)

        currency_combo.addItems(options)
        currency_combo.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(currency_combo)
        layout.addWidget(amount_widget)
        self.setLayout(layout)

        self._currency_combo_options = options
        self._currency_combo = currency_combo
        self._amount_widget = amount_widget
        self._local_api.set_payment_amount.connect(self._set_payment_amount)

    def _set_payment_amount(self, balance_widget) -> None:
        currency = balance_widget.balance_currency
        amount = balance_widget.balance_amount

        idx = self._currency_combo_options.index(currency)
        self._currency_combo.setCurrentIndex(idx)
        self._amount_widget.setText(amount)


class FundsSelectionWidget(QWidget):
    def __init__(self, local_api, parent=None):
        super().__init__(parent)
        self._local_api = local_api

        self.setObjectName("FundsSelector")

        balance = local_api.get_balance()
        sv_text, fiat_text = local_api.wallet_window.get_amount_and_units(balance)

        if fiat_text:
            column_count = 3
        else:
            column_count = 2
        model = QStandardItemModel(1, 3, self)
        model.setItem(0, 0, QStandardItem(_("All available funds")))
        sv_item = QStandardItem(sv_text)
        sv_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        model.setItem(0, 1, sv_item)
        if fiat_text:
            fiat_item = QStandardItem(fiat_text)
            fiat_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            model.setItem(0, 2, fiat_item)

        tableView = QTableView(self)
        tableView.setObjectName("FundsSelectionPopup")
        tableView.setWordWrap(False)
        tableView.setModel(model)
        tableView.verticalHeader().setVisible(False)
        tableView.horizontalHeader().setVisible(False)
        tableView.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        tableView.setAutoScroll(False)
        tableView.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        # Show more compact rows, this will actually be larger forced out by the contents to be
        # just the necessary size.
        tableView.setRowHeight(0, 20)

        combo = QComboBox()
        combo.setModel(model)
        combo.setView(tableView)
        combo.setMinimumWidth(300)

        # Detect when the combobox popup view is shown by rebinding and wrapping the method.
        def _new_showPopup(_self: QTableView) -> None:
            nonlocal old_showPopup, tableView
            old_showPopup()
            tableView.resizeColumnsToContents()

        old_showPopup = combo.showPopup
        setattr(combo, "showPopup", _new_showPopup.__get__(combo, combo.__class__))

        hlayout1 = QHBoxLayout()
        hlayout1.setSpacing(0)
        hlayout1.setContentsMargins(0, 0, 0, 2)
        hlayout1.addWidget(combo, 1)

        hlayout2 = QHBoxLayout()
        hlayout2.setSpacing(0)
        hlayout2.setContentsMargins(0, 2, 0, 0)
        balance_icon_label = QLabel("")
        balance_icon_label.setPixmap(QPixmap(icon_path("sb_balance.png")))
        balance_icon_label.setToolTip(_("The balance of the selected account."))
        hlayout2.addWidget(balance_icon_label)
        hlayout2.addSpacing(4)
        sv_balance = QLineEdit(sv_text)
        sv_balance.balance_currency = local_api.get_base_unit()
        sv_balance.balance_amount = local_api.get_base_amount(balance)
        sv_balance.setAlignment(Qt.AlignHCenter)
        sv_balance.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sv_balance.setReadOnly(True)
        hlayout2.addWidget(sv_balance)
        if fiat_text:
            hlayout2.addSpacing(4)
            fiat_balance = QLineEdit(fiat_text)
            fiat_balance.balance_currency = local_api.get_fiat_unit()
            fiat_balance.balance_amount = local_api.get_fiat_amount(balance)
            fiat_balance.setAlignment(Qt.AlignHCenter)
            fiat_balance.setReadOnly(True)
            hlayout2.addWidget(fiat_balance)

        vlayout = QVBoxLayout()
        vlayout.setSpacing(0)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.addLayout(hlayout1)
        vlayout.addLayout(hlayout2)
        self.setLayout(vlayout)

        self._sv_balance = sv_balance
        self._fiat_balance = fiat_balance

        sv_balance.installEventFilter(self)
        fiat_balance.installEventFilter(self)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

    def eventFilter(self, obj, evt):
        # Clicking a balance field sets the amount currency and the amount.
        if obj is self._sv_balance or obj is self._fiat_balance:
            if self._checkLineEditEvent(evt):
                self._local_api.set_payment_amount.emit(obj)
        return False

    def _checkLineEditEvent(self, evt: QEvent) -> bool:
        if evt.type() == QEvent.MouseButtonPress:
            return True
        if evt.type() == QEvent.KeyPress:
            if evt.key() == Qt.Key_Return or evt.key() == Qt.Key_Space or evt.key() == Qt.Key_Enter:
                return True
        return False


class PayeeBadge(QWidget):
    def __init__(self, contact, parent=None, is_interactive: bool=True) -> None:
        super().__init__(parent)

        # A QWidget has no display itself, it cannot be styled, only it's children can.

        self.name_button = name_button = QPushButton(contact.label)
        name_button.setObjectName("PayeeBadgeName")
        name_button.setAutoDefault(False)

        if is_interactive:
            view_action = QAction("View", self)
            view_action.setIcon(read_QIcon("icons8-about.svg"))
            view_action.setShortcut("Return")
            view_action.setShortcutVisibleInContextMenu(True)
            self.view_action = view_action
            # view_action.triggered.connect(self._action_view)

            clear_action = QAction("Clear", self)
            clear_action.setIcon(read_QIcon("icons8-delete.svg"))
            clear_action.setShortcut(Qt.Key_Delete)
            clear_action.setShortcutVisibleInContextMenu(True)
            self.clear_action = clear_action
            # clear_action.triggered.connect(self._action_clear)

            name_menu = QMenu()
            name_menu.addAction(view_action)
            name_menu.addAction(clear_action)
            name_button.setMenu(name_menu)

        self.system_button = system_button = QPushButton("ChainPay")
        system_button.setObjectName("PayeeBadgeSystem")
        system_button.setAutoDefault(False)

        if is_interactive:
            system_button.clicked.connect(self._on_system_button_clicked)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(name_button)
        layout.addWidget(system_button)
        self.setLayout(layout)

    def _action_view(self, checked: Optional[bool]=False) -> None:
        print("view action triggered")

    def _action_clear(self, checked: Optional[bool]=False) -> None:
        print("clear action triggered")

    def _on_system_button_clicked(self, checked: Optional[bool]=False) -> None:
        pass

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)


class PayeeSearchModel(QAbstractItemModel):
    def __init__(self, contacts, parent=None) -> None:
        super().__init__(parent)

        self._contacts = contacts

    def parent(self, model_index: QModelIndex) -> QModelIndex:
        return QModelIndex()

    def rowCount(self, model_index: QModelIndex) -> int:
        return len(self._contacts)

    def columnCount(self, model_index: QModelIndex) -> int:
        return 1

    def index(self, row: int, column: int, parent: QModelIndex) -> QModelIndex:
        if self.hasIndex(row, column, parent):
            return self.createIndex(row, column)
        return QModelIndex()

    def data(self, index: QModelIndex, role: int) -> QVariant:
        if role == Qt.EditRole:
            if index.isValid():
                return self._contacts[index.row()].label
            return None
        elif role == Qt.DisplayRole:
            if index.isValid():
                return self._contacts[index.row()].label
            return None
        return None

    def _get_contact(self, row_index: int):
        return self._contacts[row_index]


def get_source_index(model_index: QModelIndex):
    while not isinstance(model_index.model(), PayeeSearchModel):
        model_index = model_index.model().mapToSource(model_index)
    return model_index


class PayeeBadgeDelegate(QStyledItemDelegate):
    margin_x = 0
    margin_y = 0

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
            model_index: QModelIndex) -> None:
        # calculate render anchor point
        point = option.rect.topLeft()

        source_index = get_source_index(model_index)
        contact = source_index.model()._get_contact(source_index.row())
        widget = self._create_payee_badge(self.parent(), contact)
        if option.state & QStyle.State_Selected:
            p = option.palette
            p.setColor(QPalette.Background, p.color(QPalette.Active, QPalette.Highlight))
            widget.setPalette(p)
        # TODO: This appears to render with an unexpected margin at the top.
        widget.render(painter, point)

        dummyWidget = QWidget()
        widget.setParent(dummyWidget)

    def sizeHint(self, option: QStyleOptionViewItem, model_index: QModelIndex):
        # TODO: This appears to calculate an incorrect size.
        # source_index = get_source_index(model_index)
        # contact = source_index.model()._get_contact(source_index.row())
        # widget = self._create_payee_badge(self.parent(), contact)
        # size = widget.sizeHint()
        # dummyWidget = QWidget()
        # widget.setParent(dummyWidget)
        return QSize(150, 25)

    def _create_payee_badge(self, parent, contact):
        badge = PayeeBadge(contact, parent)
        return badge


class PayeeSearchWidget(QWidget):
    def __init__(self, local_api, parent=None) -> None:
        super().__init__(parent)

        self._local_api = local_api

        self.setObjectName("PayeeSearchWidget")

        contacts = local_api.get_contacts()
        self.model = PayeeSearchModel(contacts)

        edit_field = QLineEdit()
        edit_field.setMinimumWidth(200)
        edit_field.setPlaceholderText("Type a contact name here..")

        filter_model = QSortFilterProxyModel(edit_field)
        filter_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        filter_model.setSourceModel(self.model)

        contact_completer = QCompleter(filter_model, edit_field)
        contact_completer.setCompletionMode(QCompleter.PopupCompletion)
        contact_completer.setCaseSensitivity(False)
        # pylint: disable=unsubscriptable-object
        contact_completer.activated[QModelIndex].connect(self._on_entry_selected)
        edit_field.setCompleter(contact_completer)

        popup = contact_completer.popup()
        popup.setUniformItemSizes(True)
        popup.setItemDelegate(PayeeBadgeDelegate(edit_field))
        popup.setSpacing(0)
        popup.setStyleSheet("""
            .QListView {
                background-color: #F2F2F2;
                selection-background-color: #D8D8D8;
            }
        """)

        layout = QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit_field)
        self.setLayout(layout)

    def paintEvent(self, event) -> None:
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

    def _on_entry_selected(self, model_index: QModelIndex) -> None:
        source_index = get_source_index(model_index)
        contact = source_index.model()._get_contact(source_index.row())
        self.parent().set_selected_contact(contact)



class PayeeWidget(QWidget):
    MODE_SEARCH = 1
    MODE_SELECTED = 2

    def __init__(self, local_api, parent=None) -> None:
        super().__init__(parent)
        self._local_api = local_api

        self.search_widget = PayeeSearchWidget(local_api)
        self._mode = self.MODE_SEARCH

        layout = QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search_widget)
        self.setLayout(layout)

    def set_selected_contact(self, contact):
        self.badge_widget = PayeeBadge(contact, self)
        self._mode = self.MODE_SELECTED

        layout = self.layout()
        layout.addWidget(self.badge_widget)
        layout.removeWidget(self.search_widget)

        # Just removing the old widget from the layout doesn't remove it.
        dummy_widget = QWidget()
        self.search_widget.setParent(dummy_widget)

        self.setTabOrder(self._local_api.payment_window.tabs.tabBar(),
            self.badge_widget.name_button)
        self.setTabOrder(self.badge_widget.name_button, self.badge_widget.system_button)


class PaymentSectionWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.frame_layout = QVBoxLayout()

        frame = QFrame()
        frame.setObjectName("PaymentFrame")
        frame.setLayout(self.frame_layout)

        vlayout = QVBoxLayout()
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.addWidget(frame)
        self.setLayout(vlayout)

    def add_title(self, title_text: str) -> None:
        label = QLabel(title_text +":")
        label.setObjectName("PaymentSectionTitle")
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.frame_layout.addWidget(label, Qt.AlignTop)

    def add_row(self, label_text: QWidget, field_widget: QWidget,
            stretch_field: bool=False) -> None:
        line = QFrame()
        line.setObjectName("PaymentSeparatorLine")
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)

        self.frame_layout.addWidget(line)

        label = QLabel(label_text)
        label.setObjectName("PaymentSectionLabel")
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        help_label = QLabel()
        help_label.setPixmap(
            QPixmap(icon_path("icons8-help.svg")).scaledToWidth(16, Qt.SmoothTransformation))
        help_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        label_layout = QHBoxLayout()
        label_layout.addWidget(label)
        label_layout.addWidget(help_label)
        # Ensure that the top-aligned vertical spacing matches the fields.
        label_layout.setContentsMargins(0,2,0,2)
        label_layout.setSizeConstraint(QLayout.SetFixedSize)

        grid_layout = QGridLayout()
        grid_layout.addLayout(label_layout, 0, 0, Qt.AlignLeft | Qt.AlignTop)
        if stretch_field:
            grid_layout.addWidget(field_widget, 0, 1)
        else:
            field_layout = QHBoxLayout()
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.addWidget(field_widget)
            field_layout.addStretch(1)
            grid_layout.addLayout(field_layout, 0, 1)
        grid_layout.setColumnMinimumWidth(0, 80)
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setHorizontalSpacing(0)
        grid_layout.setSizeConstraint(QLayout.SetMinimumSize)

        self.frame_layout.addLayout(grid_layout)


class PaymentPayeeWidget(PaymentSectionWidget):
    def __init__(self, local_api, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("PaymentPayeeWidget")

        widget = PayeeWidget(local_api)

        self.add_title(_("Payee details"))
        self.add_row(_("Pay to"), widget)


class PaymentFundingWidget(PaymentSectionWidget):
    def __init__(self, local_api, parent=None) -> None:
        super().__init__(parent)
        self._local_api = local_api

        from_widget = FundsSelectionWidget(local_api)
        amount_widget = PaymentAmountWidget(local_api)

        self.add_title(_("Payment details"))
        self.add_row(_("Pay from"), from_widget)
        self.add_row(_("Amount"), amount_widget)


class PaymentNoteWidget(PaymentSectionWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        yours_widget = QLineEdit()
        theirs_widget = QLineEdit()
        theirs_widget.setEnabled(False)

        self.add_title(_("Payment notes"))
        self.add_row(_("Yours"), yours_widget, stretch_field=True)
        self.add_row(_("Theirs"), theirs_widget, stretch_field=True)


class PaymentDetailsFormWidget(QWidget):
    def __init__(self, local_api, parent=None) -> None:
        super().__init__(parent)

        payee_widget = PaymentPayeeWidget(local_api)

        funding_widget = PaymentFundingWidget(local_api)

        note_widget = PaymentNoteWidget()
        self.notes = note_widget

        def _on_next_tab(checked=False):
            current_index = local_api.payment_window.tabs.currentIndex()
            local_api.payment_window.tabs.setCurrentIndex(current_index+1)

        confirm_button = QPushButton(_("Next >>"))
        confirm_button.setAutoDefault(False)
        confirm_button.clicked.connect(_on_next_tab)
        confirm_button.setEnabled(False)

        confirm_layout = QHBoxLayout()
        confirm_layout.setSpacing(0)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        confirm_layout.addStretch(1)
        confirm_layout.addWidget(confirm_button)

        vlayout = QVBoxLayout()
        vlayout.addWidget(payee_widget)
        vlayout.addWidget(funding_widget)
        vlayout.addWidget(note_widget)
        vlayout.addLayout(confirm_layout)
        self.setLayout(vlayout)


class ConfirmPaymentFormWidget(QWidget):
    def __init__(self, local_api, parent=None) -> None:
        super().__init__(parent)

        vlayout = QVBoxLayout()
        self.setLayout(vlayout)


class PaymentWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        _local_api = _LocalApi(parent, self)

        self.setWindowTitle("Payment")

        self.setStyleSheet("""
        QTabWidget::right-corner {
            position: absolute;
            top: -10px;
        }

        QLabel#cornerWidget {
            font-size: 12pt;
            color: grey;
        }

        #PaymentFrame {
            background-color: #F2F2F2;
            border: 1px solid #E3E2E2;
        }

        #PaymentSectionTitle {
        }

        #PaymentSeparatorLine {
            border: 1px solid #E3E2E2;
        }

        #PaymentSectionLabel {
            color: grey;
        }

        QLineEdit:read-only {
            background-color: #F2F2F2;
        }

        QTableView#FundsSelectionPopup::item {
            padding-left: 4px;
            padding-right: 4px;
        }
        """ + payee_badge_css)

        # green for badge: 4AC41C
        # red for badge: D8634C

        enter_details_widget = PaymentDetailsFormWidget(_local_api)
        confirm_details_widget = ConfirmPaymentFormWidget(_local_api)

        # Does not look good on MacOS, due to shifted alignment.
        # corner_text = _("Make a payment")
        # corner_widget = QLabel(corner_text)
        # corner_widget.setObjectName("cornerWidget")

        self.form = enter_details_widget

        self.tabs = tabs = QTabWidget()
        # tabs.setCornerWidget(corner_widget)
        details_idx = tabs.addTab(enter_details_widget, _("Details"))
        confirm_idx = tabs.addTab(confirm_details_widget, _("Confirm"))
        tabs.setTabEnabled(confirm_idx, False)

        bbox = QDialogButtonBox(QDialogButtonBox.Close)
        bbox.rejected.connect(self.reject)
        bbox.accepted.connect(self.accept)

        close_button = bbox.button(QDialogButtonBox.Close)
        close_button.setAutoDefault(False)

        vlayout = QVBoxLayout()
        vlayout.addWidget(tabs)
        vlayout.addWidget(bbox)
        self.setLayout(vlayout)


class _LocalApi(QObject):
    set_payment_amount = pyqtSignal(object)

    def __init__(self, wallet_window, payment_window) -> None:
        self.wallet_window = wallet_window
        self.payment_window = payment_window
        super().__init__(payment_window)

    def get_contacts(self):
        return list(self.wallet_window.contacts.get_contacts())

    def get_balance(self, account_id=None) -> int:
        c, u, x = self.wallet_window.wallet.get_balance()
        return c + u

    def get_fiat_unit(self) -> Optional[str]:
        fx = app_state.fx
        if fx and fx.is_enabled():
            return fx.get_currency()

    def get_fiat_amount(self, sv_value: int) -> Optional[str]:
        fx = app_state.fx
        if fx and fx.is_enabled():
            return fx.format_amount(sv_value)

    def get_base_unit(self) -> str:
        return app_state.base_unit()

    def get_base_amount(self, sv_value: int) -> str:
        return self.wallet_window.format_amount(sv_value)

