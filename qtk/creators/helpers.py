from qtk.fields import Field as fl
import QuantLib as ql
from qtk.common import Category
from qtk.templates import Instrument
from .common import CreatorBase
from qtk.templates import Template
from . import _creatorslog


class ScheduleCreator(CreatorBase):
    _templates = [Template.SCHEDULE]
    _req_fields = [fl.ISSUE_DATE, fl.MATURITY_DATE, fl.COUPON_FREQ]
    _opt_fields = []

    def _create(self, data, asof_date):

        maturity_date = self.get(fl.MATURITY_DATE)
        issue_date = self.get(fl.ISSUE_DATE) or self.get(fl.ASOF_DATE)
        #asof_date = asof_date
        coupon_freq = self.get(fl.COUPON_FREQ)
        period = ql.Period(coupon_freq)
        calendar = self.get(fl.ACCRUAL_CALENDAR)
        convention = self.get(fl.ACCRUAL_DAY_CONVENTION)
        termination_convention = self.get(fl.TERMINATION_DAY_CONVENTION, convention)
        end_of_month = self.get(fl.END_OF_MONTH, True)

        schedule = ql.Schedule(issue_date,
                               maturity_date,
                               period,
                               calendar,
                               convention,
                               termination_convention,
                               ql.DateGeneration.Backward,
                               end_of_month)
        return schedule


class DepositRateHelperCreator(CreatorBase):
    _templates = [Template.CRV_INST_GOVT_ZCB]
    _req_fields = [fl.ISSUE_DATE, fl.MATURITY_DATE, fl.COUPON, fl.PRICE, fl.CURRENCY]
    _opt_fields = []

    def _create(self, data, asof_date):
        rate = self.get(fl.YIELD)
        maturity_date = self.get(fl.MATURITY_DATE)

        settlement_days = self.get(fl.SETTLEMENT_DAYS)
        day_count = self.get(fl.ACCRUAL_BASIS)
        convention = self.get(fl.ACCRUAL_DAY_CONVENTION)
        calendar = self.get(fl.ACCRUAL_CALENDAR)
        days = day_count.dayCount(asof_date, maturity_date)
        tenor = ql.Period(days, ql.Days)
        end_of_month = self.get(fl.END_OF_MONTH)

        depo_rate_helper = ql.DepositRateHelper(
            ql.QuoteHandle(ql.SimpleQuote(rate/100.0)),
            tenor,
            settlement_days,
            calendar,
            convention,
            end_of_month,
            day_count
        )
        return depo_rate_helper


class BondRateHelperCreator(CreatorBase):
    _templates = [Template.CRV_INST_GOVT_BOND]
    _req_fields = [fl.ISSUE_DATE, fl.MATURITY_DATE, fl.COUPON, fl.COUPON_FREQ, fl.PRICE, fl.CURRENCY]
    _opt_fields = []

    def _create(self, data, asof_date):
        schedule = ScheduleCreator(data).create(asof_date)
        face_amount = self.get(fl.FACE_AMOUNT, 100.0)
        settlement_days = self.get(fl.SETTLEMENT_DAYS)
        day_count = self.get(fl.ACCRUAL_BASIS)
        convention = self.get(fl.ACCRUAL_DAY_CONVENTION)
        price = self.get(fl.PRICE)
        coupon = self.get(fl.COUPON)
        bond_helper = ql.FixedRateBondHelper(
            ql.QuoteHandle(ql.SimpleQuote(price)),
            settlement_days,
            face_amount,
            schedule,
            [coupon/100.0],
            day_count,
            convention
        )
        return bond_helper


class BondYieldCurveCreator(CreatorBase):
    # required fields
    _templates = [Template.TS_YIELD_BOND]
    _req_fields = [fl.INSTRUMENT_COLLECTION, fl.ASOF_DATE, fl.COUNTRY, fl.CURRENCY]
    _opt_fields = [fl.INTERPOLATION_METHOD]
    _values = {fl.INTERPOLATION_METHOD.id: ["LinearZero", "CubicZero", "FlatForward",
                                            "LinearForward", "LogCubicDiscount"]}

    # class data
    _interpolator_map = {
        "LinearZero": ql.PiecewiseLinearZero,
        "CubicZero": ql.PiecewiseCubicZero,
        "FlatForward": ql.PiecewiseFlatForward,
        "LinearForward": ql.PiecewiseLinearForward,
        "LogCubicDiscount": ql.PiecewiseLogCubicDiscount
    }

    def _create(self, data, asof_date):
        curve_members = data[fl.INSTRUMENT_COLLECTION.id]
        rate_helpers = []
        intepolator = data.get(fl.INTERPOLATION_METHOD.id, "LinearZero")
        for c in curve_members:
            instance = c.get(fl.TEMPLATE.id)
            loc_asof_date = self.get(fl.ASOF_DATE, asof_date)
            try:
                if isinstance(instance, Instrument) and (instance.security_subtype == Category.ZCB):
                    depo_rate_helper = DepositRateHelperCreator(c).create(loc_asof_date)
                    rate_helpers.append(depo_rate_helper)
                elif isinstance(instance, Instrument) and (instance.security_subtype == Category.BOND):
                    bond_rate_helper = BondRateHelperCreator(c).create(loc_asof_date)
                    rate_helpers.append(bond_rate_helper)
            except Exception as e:
                _creatorslog.exception(e)

        day_count = ql.Actual360()

        yc_method = self._interpolator_map[intepolator]
        yc_curve = yc_method(
            asof_date,
            rate_helpers,
            day_count
        )

        return yc_curve
