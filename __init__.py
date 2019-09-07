"""Classy Portfolio extension for Fava.

"""
import os
import re

from beancount.core.data import iter_entry_dates, Open, Commodity
from beancount.core.number import ZERO, Decimal

from fava.ext import FavaExtensionBase
from fava.template_filters import cost_or_value
from fava.core.tree import Tree
from fava.core.helpers import FavaAPIException
from fava.application import app


class FavaClassyPortfolio(FavaExtensionBase):  # pragma: no cover
    """Fava Extension Report that prints out a portfolio list based
       on asset-class and asset-subclass metadata.
    """

    report_title = "Classy Portfolio"

    def load_report(self):
        # self.account_open_dict = {entry.account: entry for entry in
                                  # self.ledger.all_entries_by_type[Open]}
        self.commodity_dict = {entry.currency: entry for entry in
                               self.ledger.all_entries_by_type[Commodity]}

    def portfolio_accounts(self, begin=None, end=None):
        """An account tree based on matching regex patterns."""
        self.load_report()

        if begin:
            tree = Tree(iter_entry_dates(self.ledger.entries, begin, end))
        else:
            tree = self.ledger.root_tree

        portfolios = []

        for option in self.config:
            opt_key = option[0]
            if opt_key == "account_name_pattern":
                portfolio = self._account_name_pattern(tree, end, option[1])
            elif opt_key == "account_open_metadata_pattern":
                portfolio = self._account_metadata_pattern(
                    tree, end, option[1][0], option[1][1]
                )
            else:
                raise FavaAPIException("Classy Portfolio: Invalid option.")

            portfolio = (portfolio[0],
                         (insert_rowspans(
                             portfolio[1][0],
                             portfolio[1][1],
                             True),
                          portfolio[1][1])
                         )
            portfolios.append(portfolio)

        return portfolios

    def _account_name_pattern(self, tree, date, pattern):
        """
        Returns portfolio info based on matching account name.

        Args:
            tree: Ledger root tree node.
            date: Date.
            pattern: Account name regex pattern.
        Return:
            Data structured for use with a querytable (types, rows).
        """
        title = "Account names matching: '" + pattern + "'"
        selected_accounts = []
        regexer = re.compile(pattern)
        for acct in tree.keys():
            if (regexer.match(acct) is not None) and (
                acct not in selected_accounts
            ):
                selected_accounts.append(acct)

        selected_nodes = [tree[x] for x in selected_accounts]
        portfolio_data = self._portfolio_data(selected_nodes, date)
        return title, portfolio_data

    def _account_metadata_pattern(self, tree, date, metadata_key, pattern):
        """
        Returns portfolio info based on matching account open metadata.

        Args:
            tree: Ledger root tree node.
            date: Date.
            metadata_key: Metadata key to match for in account open.
            pattern: Metadata value's regex pattern to match for.
        Return:
            Data structured for use with a querytable - (types, rows).
        """
        title = (
            "Accounts with '"
            + metadata_key
            + "' metadata matching: '"
            + pattern
            + "'"
        )
        selected_accounts = []
        regexer = re.compile(pattern)
        for entry in self.ledger.all_entries_by_type[Open]:
            if (metadata_key in entry.meta) and (
                regexer.match(entry.meta[metadata_key]) is not None
            ):
                selected_accounts.append(entry.account)

        selected_nodes = [tree[x] for x in selected_accounts]
        portfolio_data = self._portfolio_data(selected_nodes, date)
        return title, portfolio_data

    def _portfolio_data(self, nodes, date):
        """
        Turn a portfolio of tree nodes into portfolio_table-style data,
        looking at account 'asset_class' and 'asset_subclass' data.

        Args:
            nodes: Account tree nodes.
            date: Date.
        Return:
            types: Tuples of column names and types as strings.
            rows: Dictionaries of row data by column names.
        """
        errors = []
        operating_currency = self.ledger.options["operating_currency"][0]

        types = [
            ("portfolio_total", str(Decimal)),
            ("asset_classes", str(dict)),
            ("portfolio_allocation", str(Decimal)),
            ("asset_class_total", str(Decimal)),
            ("asset_subclasses", str(dict)),
            # ("portfolio_allocation", str(Decimal)),
            ("asset_class_allocation", str(Decimal)),
            ("asset_subclass_total", str(Decimal)),
            ("accounts", str(dict)),
            # ("portfolio_allocation", str(Decimal)),
            # ("class_allocation", str(Decimal)),
            ("asset_subclass_allocation", str(Decimal)),
            ("balance", str(Decimal))
        ]

        portfolio_tree = {}
        portfolio_tree["portfolio_total"] = ZERO
        portfolio_tree["asset_classes"] = {}
        for node in nodes:
            commodity = node_commodity(node)
            if (commodity in self.commodity_dict) and (
               "asset-class" in self.commodity_dict[commodity].meta
               ):
                asset_class = self.commodity_dict[
                    commodity].meta["asset-class"]
            else:
                asset_class = "noclass"

            if (commodity in self.commodity_dict) and (
               "asset-subclass" in self.commodity_dict[commodity].meta
               ):
                asset_subclass = self.commodity_dict[
                    commodity].meta["asset-subclass"]
            else:
                asset_subclass = "nosubclass"

            if asset_class not in portfolio_tree["asset_classes"]:
                portfolio_tree["asset_classes"][asset_class] = {}
                portfolio_tree["asset_classes"][asset_class][
                    "portfolio_allocation"] = ZERO
                portfolio_tree["asset_classes"][asset_class][
                    "asset_class_total"] = ZERO
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"] = {}
            if asset_subclass not in portfolio_tree[
                    "asset_classes"][asset_class]["asset_subclasses"]:
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass] = {}
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass][
                    "asset_subclass_total"] = ZERO
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass][
                    "portfolio_allocation"] = ZERO
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass][
                    "asset_subclass_asset_class_allocation"] = ZERO
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass][
                    "accounts"] = {}

            # Insert account-level balances and
            # Sum totals for later calculating allocation
            account_data = {}
            balance = cost_or_value(node.balance, date)
            if operating_currency in balance:
                balance_dec = balance[operating_currency]
                account_data["balance"] = balance_dec
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass][
                    "accounts"][node.name] = account_data

                portfolio_tree["portfolio_total"] += balance_dec
                portfolio_tree["asset_classes"][asset_class][
                    "asset_class_total"] += balance_dec
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass][
                    "asset_subclass_total"] += balance_dec

            elif len(balance) == 0:
                # Assume account is empty
                account_data["balance"] = ZERO
                portfolio_tree["asset_classes"][asset_class][
                    "asset_subclasses"][asset_subclass][
                    "accounts"][node.name] = account_data
            else:
                errors.append("account " + node.name +
                              " has balances not in operating currency " +
                              operating_currency)

        # Now that account balances and totals are calculated,
        # Traverse and calculate portfolio-level info.
        for asset_class in portfolio_tree["asset_classes"]:
            asset_class_dict = portfolio_tree["asset_classes"][asset_class]

            asset_class_dict["portfolio_allocation"] = ZERO if portfolio_tree["portfolio_total"] == ZERO else round(
                (asset_class_dict["asset_class_total"] /
                 portfolio_tree["portfolio_total"]) * 100, 2
            )

            for asset_subclass in asset_class_dict["asset_subclasses"]:
                asset_subclass_dict = asset_class_dict[
                    "asset_subclasses"][asset_subclass]

                asset_subclass_dict["portfolio_allocation"] = ZERO if portfolio_tree["portfolio_total"] == ZERO else round(
                    (asset_subclass_dict["asset_subclass_total"] /
                        portfolio_tree["portfolio_total"]) * 100, 2
                )

                asset_subclass_dict["asset_class_allocation"] = ZERO if asset_class_dict["asset_class_total"] == ZERO else round(
                    (asset_subclass_dict["asset_subclass_total"] /
                        asset_class_dict["asset_class_total"]) * 100, 2
                )

                for account in asset_subclass_dict["accounts"]:
                    account_dict = asset_subclass_dict["accounts"][account]

                    account_dict["portfolio_allocation"] = ZERO if portfolio_tree["portfolio_total"] == ZERO else round(
                        (account_dict["balance"] /
                            portfolio_tree["portfolio_total"]) * 100, 2
                    )

                    account_dict["asset_class_allocation"] = ZERO if asset_class_dict["asset_class_total"] == ZERO else round(
                        (account_dict["balance"] /
                            asset_class_dict["asset_class_total"]) * 100, 2
                    )

                    account_dict["asset_subclass_allocation"] = ZERO if asset_subclass_dict["asset_subclass_total"] == ZERO else round(
                        (account_dict["balance"] /
                            asset_subclass_dict["asset_subclass_total"]) * 100, 2
                    )

        return portfolio_tree, types, errors


def node_commodity(node):
    """
    Return the common 'commodity' in an account.
    Return 'mixed_commodities' if an account has multiple commodities.
    """
    if len(node.balance):
        currencies = [cost[0] for cost in list(node.balance.keys())]
        ref_currency = currencies[0]
        for currency in currencies:
            if currency != ref_currency:
                return 'mixed_commodities'
        return ref_currency
    else:
        return ''


def insert_rowspans(data, coltypes, isStart):
    new_data = {}
    colcount = 0

    if(isStart):
        # if starting, we start traversing the data by coltype
        for coltype in coltypes:
            if(coltype[1] == "<class 'dict'>"):
                # Recurse and call rowspans again
                new_data_inner = insert_rowspans(data[coltype[0]],
                                                 coltypes[(colcount + 1):],
                                                 False)

                # Collect the results
                new_data[coltype[0]] = new_data_inner
                rowsum = 0
                for value in new_data_inner.values():
                    rowsum += value[1]["rowspan"]

                # append sum of columns to prior columns
                for i in list(range(0, colcount, 1)):
                    new_data[coltypes[i][0]] = (
                        new_data[coltypes[i][0]][0], {"rowspan": rowsum})
                break

            else:
                # assume non-dict, row-span of 1 as placeholder
                new_data[coltype[0]] = (data[coltype[0]], {"rowspan": 1})

            colcount = colcount + 1

    else:
        # Assume start data is a (multi-key) dictionary and we need to go
        # through the keys

        # reformat data for dict to have rowspan data
        for key in data.keys():
            new_data[key] = (data[key], {"rowspan": 1})

        for coltype in coltypes:
            if(coltype[1] == "<class 'dict'>"):
                # Return length of each key.
                for key in data.keys():
                    new_data_inner = insert_rowspans(data[key][coltype[0]],
                                                     coltypes[(colcount + 1):],
                                                     False)
                    new_data[key][0][coltype[0]] = new_data_inner

                    rowsum = 0
                    for value in new_data_inner.values():
                        rowsum += value[1]["rowspan"]

                    # Backpropagate rowspans to earlier coltypes...
                    for i in list(range(0, colcount, 1)):
                        new_data[key][0][coltypes[i][0]] = (
                            new_data[key][0][coltypes[i][0]][
                                0], {"rowspan": rowsum}
                        )
                    # ...including the dictionary key
                    new_data[key] = (new_data[key][0], {"rowspan": rowsum})
                break

            else:
                # placeholder for each key
                for key in data.keys():
                    new_data[key][0][coltype[0]] = (
                        data[key][coltype[0]], {"rowspan": 1})

            colcount = colcount + 1

    return new_data
