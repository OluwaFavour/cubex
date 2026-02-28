from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, computed_field, Field


def coerce_timestamp_to_datetime(ts: int) -> datetime:
    """Converts a Unix timestamp (in seconds) to a datetime object."""
    if isinstance(ts, int):
        return datetime.fromtimestamp(ts)
    return ts


class ListResponse(BaseModel):
    has_more: bool
    url: str


class Product(BaseModel):
    id: str
    name: str
    description: str | None = None
    active: bool
    default_price: str | None = None
    metadata: dict[str, Any] = {}
    tax_code: str | None = None
    created: Annotated[datetime, BeforeValidator(coerce_timestamp_to_datetime)]
    updated: Annotated[datetime, BeforeValidator(coerce_timestamp_to_datetime)]


class ProductListResponse(ListResponse):
    data: list[Product]


class Recurring(BaseModel):
    interval: Literal["day", "week", "month", "year"]
    interval_count: int
    meter: str | None = None
    usage_type: Literal["licensed", "metered"]


class RecurringWithoutCount(BaseModel):
    interval: Literal["day", "week", "month", "year"]
    meter: str | None = None
    usage_type: Literal["licensed", "metered"]


class CustomUnitAmount(BaseModel):
    maximum: int | None = None
    minimum: int | None = None
    preset: int | None = None


class CustomUnitAmountEnabled(CustomUnitAmount):
    enabled: bool = True


class Tier(BaseModel):
    flat_amount: int | None = None
    flat_amount_decimal: Decimal | None = None
    unit_amount: int | None = None
    unit_amount_decimal: Decimal | None = None
    up_to: int | None = None


class CurrencyOptions(BaseModel):
    custom_unit_amount: CustomUnitAmount | CustomUnitAmountEnabled | None = None
    tax_behavior: Literal["inclusive", "exclusive", "unspecified"] | None = None
    tiers: list[Tier] | None = None
    unit_amount: int | None = None
    unit_amount_decimal: Decimal | None = None


class CurrencyOptionsCustomUnitAmountEnabled(CurrencyOptions):
    custom_unit_amount: CustomUnitAmountEnabled | None = None  # type: ignore[assignment]


class TransformQuantity(BaseModel):
    divide_by: int
    round: Literal["up", "down"]


class Price(BaseModel):
    id: str
    active: bool
    currency: str
    metadata: dict[str, Any] = {}
    nickname: str | None = None
    product: str | Product
    recurring: Recurring | None = None
    tax_behavior: Literal["inclusive", "exclusive", "unspecified"] | None = None
    type: Literal["one_time", "recurring"]
    unit_amount: int | None = None
    billing_scheme: Literal["per_unit", "tiered"] | None = None
    created: Annotated[datetime, BeforeValidator(coerce_timestamp_to_datetime)]
    currency_options: dict[str, CurrencyOptions] | None = None
    custom_unit_amount: CustomUnitAmount | None = None
    livemode: bool
    lookup_key: str | None = None
    tiers: list[Tier] | None = None
    tiers_mode: Literal["graduated", "volume"] | None = None
    transform_quantity: TransformQuantity | None = None
    unit_amount_decimal: Decimal | None = None


class PriceListResponse(ListResponse):
    data: list[Price]


class InvoiceLineItemParentSubscriptionItemDetails(BaseModel):
    proration: Annotated[
        bool, Field(description="Indicates if the line item is a proration.")
    ]


class InvoiceLineItemParent(BaseModel):
    subscription_item_details: Annotated[
        InvoiceLineItemParentSubscriptionItemDetails | None,
        Field(
            description="Details about the subscription item associated with this line item."
        ),
    ] = None


class InvoiceLineItem(BaseModel):
    id: Annotated[
        str, Field(description="Unique identifier for the invoice line item.")
    ]
    amount: Annotated[int, Field(description="Amount for the line item in cents.")]
    currency: Annotated[
        str, Field(description="Three-letter ISO currency code, in lowercase.")
    ]
    description: Annotated[
        str | None, Field(description="Description of the line item.")
    ] = None
    parent: Annotated[
        InvoiceLineItemParent | None,
        Field(description="The parent object of the line item."),
    ] = None


class ListInvoiceLineItems(ListResponse):
    data: list[InvoiceLineItem]


class Invoice(BaseModel):
    """Simplified Stripe Invoice object with essential fields for subscription history."""

    id: Annotated[str, Field(description="Unique identifier for the invoice.")]
    object: Annotated[
        Literal["invoice"],
        Field(description="String representing the object's type. Always 'invoice'."),
    ] = "invoice"
    amount_due: Annotated[
        int,
        Field(
            description="Final amount due at this time for this invoice in cents. If the invoice's total is smaller than the minimum charge amount, this value will be 0."
        ),
    ]
    amount_paid: Annotated[
        int,
        Field(
            description="The amount, in cents, that was paid. This is the sum of all payments."
        ),
    ]
    created: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]
    currency: Annotated[
        str,
        Field(
            description="Three-letter ISO currency code, in lowercase. Must be a supported currency."
        ),
    ]
    customer: Annotated[
        str | None,
        Field(description="The ID of the customer who will be billed."),
    ] = None
    hosted_invoice_url: Annotated[
        str | None,
        Field(
            description="The URL for the hosted invoice page, which allows customers to view and pay an invoice."
        ),
    ] = None
    invoice_pdf: Annotated[
        str | None,
        Field(description="The link to download the PDF for the invoice."),
    ] = None
    lines: Annotated[
        ListInvoiceLineItems | None, Field(description="The invoice line items.")
    ] = None
    number: Annotated[
        str | None,
        Field(
            description="A unique, identifying string that appears on emails sent to the customer for this invoice."
        ),
    ] = None
    period_end: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(description="End of the billing period for the invoice."),
    ]
    period_start: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(description="Start of the billing period for the invoice."),
    ]
    status: Annotated[
        Literal["draft", "open", "paid", "uncollectible", "void"] | None,
        Field(
            description="The status of the invoice, one of draft, open, paid, uncollectible, or void."
        ),
    ] = None
    total: Annotated[
        int, Field(description="The total amount of the invoice in cents.")
    ]

    @computed_field
    @property
    def proration_amount(self) -> Decimal:
        amount: int = 0
        if self.lines and self.lines.data:
            for line in self.lines.data:
                if (
                    line.parent
                    and line.parent.subscription_item_details
                    and line.parent.subscription_item_details.proration
                ):
                    amount += line.amount

        return (Decimal(amount) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class InvoiceListResponse(ListResponse):
    data: list[Invoice]


class Customer(BaseModel):
    """Simplified Stripe Customer object with essential fields."""

    id: Annotated[str, Field(description="Unique identifier for the customer.")]
    object: Annotated[
        Literal["customer"],
        Field(description="String representing the object's type. Always 'customer'."),
    ] = "customer"
    email: Annotated[
        str | None,
        Field(description="The customer's email address."),
    ] = None
    name: Annotated[
        str | None,
        Field(description="The customer's full name or business name."),
    ] = None
    created: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]
    default_source: Annotated[
        str | None,
        Field(description="ID of the default payment source for the customer."),
    ] = None
    invoice_settings: Annotated[
        dict[str, Any],
        Field(description="The customer's default invoice settings."),
    ] = {}
    metadata: Annotated[
        dict[str, Any],
        Field(description="Set of key-value pairs attached to the object."),
    ] = {}
    livemode: Annotated[
        bool,
        Field(
            description="Has the value true if the object exists in live mode or the value false if the object exists in test mode."
        ),
    ]


class BillingPortalSession(BaseModel):
    """Stripe Customer Portal Session object."""

    id: Annotated[str, Field(description="Unique identifier for the session.")]
    object: Annotated[
        Literal["billing_portal.session"],
        Field(
            description="String representing the object's type. Always 'billing_portal.session'."
        ),
    ] = "billing_portal.session"
    configuration: Annotated[
        str,
        Field(description="The configuration used by this session."),
    ]
    created: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]
    customer: Annotated[
        str,
        Field(description="The ID of the customer for this session."),
    ]
    livemode: Annotated[
        bool,
        Field(
            description="Has the value true if the object exists in live mode or the value false if the object exists in test mode."
        ),
    ]
    return_url: Annotated[
        str | None,
        Field(
            description="The URL to redirect customers to when they click on the portal's link to return to your website."
        ),
    ] = None
    url: Annotated[
        str,
        Field(
            description="The short-lived URL of the session that gives customers access to the customer portal."
        ),
    ]


def validate_statement_descriptor(v: str | None) -> str | None:
    """Validates that the statement descriptor is at most 22 characters."""
    forbidden_characters = ["<", ">", '"', "'", "\\"]
    if v is not None:
        if len(v) > 22:
            raise ValueError("Statement descriptor must be at most 22 characters")
        if any(char in v for char in forbidden_characters):
            raise ValueError(
                f"Statement descriptor cannot contain the following characters: {' '.join(forbidden_characters)}"
            )
    return v


class ProductData(BaseModel):
    name: str
    active: bool = True
    metadata: dict[str, Any] | None = None
    statement_descriptor: Annotated[
        str | None, AfterValidator(validate_statement_descriptor)
    ] = None
    tax_code: str | None = None
    unit_label: str | None = None


class Liability(BaseModel):
    account: str | None = None
    type: Literal["account", "self"]


class AutomaticTax(BaseModel):
    enabled: bool
    liability: Liability | None = None
    provider: str | None = None
    status: Literal["complete", "failed", "requires_location_inputs"] | None = None


class AdjustableQuantity(BaseModel):
    enabled: bool
    minimum: int | None = None
    maximum: int | None = None


class ProductDataInline(BaseModel):
    name: str
    description: str | None = None
    images: list[str] | None = None
    metadata: dict[str, Any] | None = None
    tax_code: str | None = None
    unit_label: str | None = None


class RecurringInline(BaseModel):
    interval: Literal["day", "week", "month", "year"]
    interval_count: int


class PriceData(BaseModel):
    currency: str
    product: str | None = None
    product_data: ProductDataInline | dict[str, Any] | None = None
    recurring: RecurringInline | dict[str, Any] | None = None
    tax_behavior: Literal["inclusive", "exclusive", "unspecified"] | None = None
    unit_amount: int | None = None
    unit_amount_decimal: Decimal | None = None


class LineItem(BaseModel):
    adjustable_quantity: AdjustableQuantity | dict[str, Any] | None = None
    dynamic_tax_rates: list[str] | None = None
    price: str | None = None
    price_data: PriceData | dict[str, Any] | None = None
    quantity: int | None = None
    tax_rates: list[str] | None = None


class AfterExpirationRecovery(BaseModel):
    """Configuration used to recover the Checkout Session on expiry."""

    allow_promotion_codes: Annotated[
        bool | None,
        Field(
            description="Enables user redeemable promotion codes on the recovered Checkout Sessions."
        ),
    ] = None
    enabled: Annotated[
        bool,
        Field(
            description="If `true`, a recovery url will be generated to recover this Checkout Session if it expires before a transaction is completed."
        ),
    ]
    expires_at: Annotated[
        int | None,
        Field(description="The timestamp at which the recovery URL will expire."),
    ] = None
    url: Annotated[
        str | None,
        Field(
            description="URL that creates a new Checkout Session when clicked that is a copy of this expired Checkout Session."
        ),
    ] = None


class AfterExpiration(BaseModel):
    """Configuration for actions to take if this Checkout Session expires."""

    recovery: Annotated[
        AfterExpirationRecovery | None,
        Field(
            description="When set, configuration used to recover the Checkout Session on expiry."
        ),
    ] = None


class Discount(BaseModel):
    """Coupon or promotion code attached to the Checkout Session."""

    id: Annotated[
        str | None, Field(description="Unique identifier for the discount.")
    ] = None
    coupon: Annotated[
        str | None, Field(description="Coupon attached to the Checkout Session.")
    ] = None
    promotion_code: Annotated[
        str | None,
        Field(description="Promotion code attached to the Checkout Session."),
    ] = None


class CustomerAddress(BaseModel):
    """Customer address details."""

    city: Annotated[
        str | None, Field(description="City, district, suburb, town, or village.")
    ] = None
    country: Annotated[
        str | None, Field(description="Two-letter country code (ISO 3166-1 alpha-2).")
    ] = None
    line1: Annotated[
        str | None,
        Field(
            description="Address line 1, such as the street, PO Box, or company name."
        ),
    ] = None
    line2: Annotated[
        str | None,
        Field(
            description="Address line 2, such as the apartment, suite, unit, or building."
        ),
    ] = None
    postal_code: Annotated[str | None, Field(description="ZIP or postal code.")] = None
    state: Annotated[
        str | None, Field(description="State, county, province, or region.")
    ] = None


class CustomerTaxID(BaseModel):
    """Customer tax ID information."""

    type: Annotated[
        str, Field(description="The type of the tax ID (e.g., 'us_ein', 'eu_vat').")
    ]
    value: Annotated[str | None, Field(description="The value of the tax ID.")] = None


class CustomerDetails(BaseModel):
    """Customer details collected in the Checkout Session."""

    address: Annotated[
        CustomerAddress | None,
        Field(description="The customer's address after a completed Checkout Session."),
    ] = None
    business_name: Annotated[
        str | None,
        Field(
            description="The customer's business name after a completed Checkout Session."
        ),
    ] = None
    email: Annotated[
        str | None,
        Field(description="The email associated with the Customer, if one exists."),
    ] = None
    individual_name: Annotated[
        str | None,
        Field(
            description="The customer's individual name after a completed Checkout Session."
        ),
    ] = None
    name: Annotated[
        str | None,
        Field(description="The customer's name after a completed Checkout Session."),
    ] = None
    phone: Annotated[
        str | None,
        Field(
            description="The customer's phone number after a completed Checkout Session."
        ),
    ] = None
    tax_exempt: Annotated[
        Literal["exempt", "none", "reverse"] | None,
        Field(description="The customer's tax exempt status."),
    ] = None
    tax_ids: Annotated[
        list[CustomerTaxID] | None,
        Field(description="The customer's tax IDs after a completed Checkout Session."),
    ] = None


class ConsentResult(BaseModel):
    """Result of consent collection for this session."""

    promotions: Annotated[
        Literal["opt_in", "opt_out"] | None,
        Field(description="Customer consent status for promotional communications."),
    ] = None
    terms_of_service: Annotated[
        Literal["accepted"] | None,
        Field(description="Customer acceptance of terms of service."),
    ] = None


class PaymentMethodReuseAgreement(BaseModel):
    """Payment method reuse agreement configuration."""

    position: Annotated[
        Literal["auto", "hidden"],
        Field(
            description="Position and visibility of the payment method reuse agreement in the UI."
        ),
    ]


class ConsentCollection(BaseModel):
    """Configuration for Checkout to gather active consent from customers."""

    payment_method_reuse_agreement: Annotated[
        PaymentMethodReuseAgreement | None,
        Field(description="Configuration for payment method reuse agreement."),
    ] = None
    promotions: Annotated[
        Literal["auto", "none"] | None,
        Field(description="Whether to collect consent for promotional communications."),
    ] = None
    terms_of_service: Annotated[
        Literal["none", "required"] | None,
        Field(description="Whether to require acceptance of terms of service."),
    ] = None


class ShippingAddressCollection(BaseModel):
    """Configuration for Checkout to collect a shipping address."""

    allowed_countries: Annotated[
        list[str],
        Field(
            description="An array of two-letter ISO country codes representing which countries Checkout should provide as options for shipping locations."
        ),
    ]


class ShippingCostTaxRate(BaseModel):
    """Tax rate applied to shipping cost."""

    id: Annotated[str, Field(description="Unique identifier for the tax rate.")]
    active: Annotated[bool, Field(description="Whether the tax rate is active.")]
    country: Annotated[
        str | None,
        Field(description="Two-letter country code (ISO 3166-1 alpha-2)."),
    ] = None
    percentage: Annotated[
        float,
        Field(description="Tax rate percentage out of 100."),
    ]


class ShippingCostTax(BaseModel):
    """Tax applied to shipping."""

    amount: Annotated[int, Field(description="Amount of tax applied for this rate.")]
    rate: Annotated[ShippingCostTaxRate, Field(description="The tax rate applied.")]


class ShippingCost(BaseModel):
    """Details of customer cost of shipping."""

    amount_subtotal: Annotated[
        int,
        Field(
            description="Total shipping cost before any discounts or taxes are applied."
        ),
    ]
    amount_tax: Annotated[
        int, Field(description="Total tax amount applied due to shipping costs.")
    ]
    amount_total: Annotated[
        int,
        Field(description="Total shipping cost after discounts and taxes are applied."),
    ]
    shipping_rate: Annotated[
        str | None, Field(description="The ID of the ShippingRate for this order.")
    ] = None
    taxes: Annotated[
        list[ShippingCostTax] | None,
        Field(description="The taxes applied to the shipping rate."),
    ] = None


class CustomFieldDropdownOption(BaseModel):
    """Option for dropdown custom field."""

    label: Annotated[str, Field(description="The label for the option.")]
    value: Annotated[str, Field(description="The value for this option.")]


class CustomFieldDropdown(BaseModel):
    """Configuration for dropdown custom field."""

    default_value: Annotated[
        str | None,
        Field(description="The value that will pre-fill on the payment page."),
    ] = None
    options: Annotated[
        list[CustomFieldDropdownOption],
        Field(description="The options available for the customer to select."),
    ]
    value: Annotated[
        str | None,
        Field(description="The option selected by the customer."),
    ] = None


class CustomFieldNumeric(BaseModel):
    """Configuration for numeric custom field."""

    default_value: Annotated[
        str | None, Field(description="The value that will pre-fill the field.")
    ] = None
    maximum_length: Annotated[
        int | None,
        Field(
            description="The maximum character length constraint for the customer's input."
        ),
    ] = None
    minimum_length: Annotated[
        int | None,
        Field(
            description="The minimum character length requirement for the customer's input."
        ),
    ] = None
    value: Annotated[
        str | None,
        Field(description="The value entered by the customer, containing only digits."),
    ] = None


class CustomFieldText(BaseModel):
    """Configuration for text custom field."""

    default_value: Annotated[
        str | None, Field(description="The value that will pre-fill the field.")
    ] = None
    maximum_length: Annotated[
        int | None,
        Field(
            description="The maximum character length constraint for the customer's input."
        ),
    ] = None
    minimum_length: Annotated[
        int | None,
        Field(
            description="The minimum character length requirement for the customer's input."
        ),
    ] = None
    value: Annotated[
        str | None,
        Field(description="The value entered by the customer."),
    ] = None


class CustomFieldLabel(BaseModel):
    """Label configuration for custom field."""

    custom: Annotated[
        str | None,
        Field(description="Custom text for the label, displayed to the customer."),
    ] = None
    type: Annotated[
        Literal["custom"],
        Field(description="The type of the label."),
    ]


class CustomField(BaseModel):
    """Custom field collected from customer."""

    dropdown: Annotated[
        CustomFieldDropdown | None,
        Field(description="Configuration for `type=dropdown` fields."),
    ] = None
    key: Annotated[
        str,
        Field(
            description="String of your choice that your integration can use to reconcile this field."
        ),
    ]
    label: Annotated[
        CustomFieldLabel,
        Field(description="The label for the field, displayed to the customer."),
    ]
    numeric: Annotated[
        CustomFieldNumeric | None,
        Field(description="Configuration for `type=numeric` fields."),
    ] = None
    optional: Annotated[
        bool,
        Field(
            description="Whether the customer is required to complete the field before completing the Checkout Session."
        ),
    ]
    text: Annotated[
        CustomFieldText | None,
        Field(description="Configuration for `type=text` fields."),
    ] = None
    type: Annotated[
        Literal["dropdown", "numeric", "text"],
        Field(description="The type of the field."),
    ]


class CustomTextMessage(BaseModel):
    """Custom text message."""

    message: Annotated[str, Field(description="Text message (maximum 500 characters).")]


class CustomText(BaseModel):
    """Display additional text for your customers."""

    after_submit: Annotated[
        CustomTextMessage | None,
        Field(
            description="Custom text that should be displayed after the payment confirmation button."
        ),
    ] = None
    shipping_address: Annotated[
        CustomTextMessage | None,
        Field(
            description="Custom text that should be displayed alongside shipping address collection."
        ),
    ] = None
    submit: Annotated[
        CustomTextMessage | None,
        Field(
            description="Custom text that should be displayed alongside the payment confirmation button."
        ),
    ] = None
    terms_of_service_acceptance: Annotated[
        CustomTextMessage | None,
        Field(
            description="Custom text that should be displayed in place of the default terms of service agreement text."
        ),
    ] = None


class BrandingImage(BaseModel):
    """Branding image configuration."""

    file: Annotated[
        str | None,
        Field(description="The ID of a File upload representing the image."),
    ] = None
    type: Annotated[
        Literal["file", "url"],
        Field(description="The type of image for the icon/logo."),
    ]
    url: Annotated[
        str | None,
        Field(description="The URL of the image when `type` is `url`."),
    ] = None


class BrandingSettings(BaseModel):
    """Branding settings for the Checkout Session."""

    background_color: Annotated[
        str | None,
        Field(
            description="A hex color value starting with `#` representing the background color."
        ),
    ] = None
    border_style: Annotated[
        Literal["pill", "rectangular", "rounded"] | None,
        Field(description="The border style for the Checkout Session."),
    ] = None
    button_color: Annotated[
        str | None,
        Field(
            description="A hex color value starting with `#` representing the button color."
        ),
    ] = None
    display_name: Annotated[
        str | None,
        Field(description="The display name shown on the Checkout Session."),
    ] = None
    font_family: Annotated[
        str | None,
        Field(description="The font family for the Checkout Session."),
    ] = None
    icon: Annotated[
        BrandingImage | None,
        Field(description="The icon for the Checkout Session."),
    ] = None
    logo: Annotated[
        BrandingImage | None,
        Field(description="The logo for the Checkout Session."),
    ] = None


class WalletOptionsLink(BaseModel):
    """Link wallet configuration."""

    display: Annotated[
        Literal["auto", "never"] | None,
        Field(description="Whether Checkout should display Link."),
    ] = None


class WalletOptions(BaseModel):
    """Wallet-specific configuration for this Checkout Session."""

    link: Annotated[
        WalletOptionsLink | None,
        Field(description="Link wallet configuration."),
    ] = None


class PhoneNumberCollection(BaseModel):
    """Phone number collection configuration."""

    enabled: Annotated[
        bool,
        Field(
            description="Whether phone number collection is enabled for the session."
        ),
    ]


class NameCollectionSettings(BaseModel):
    """Name collection settings."""

    enabled: Annotated[
        bool,
        Field(description="Whether name collection is enabled for the session."),
    ]
    optional: Annotated[
        bool,
        Field(
            description="Whether the customer is required to complete the field before completing the Checkout Session."
        ),
    ]


class NameCollection(BaseModel):
    """Name collection configuration."""

    business: Annotated[
        NameCollectionSettings | None,
        Field(description="Settings for collecting a business's name."),
    ] = None
    individual: Annotated[
        NameCollectionSettings | None,
        Field(description="Settings for collecting an individual's name."),
    ] = None


class TaxIDCollection(BaseModel):
    """Tax ID collection configuration."""

    enabled: Annotated[
        bool,
        Field(description="Whether tax ID collection is enabled for the session."),
    ]
    required: Annotated[
        Literal["if_supported", "never"] | None,
        Field(description="Whether a tax ID is required on the payment page."),
    ] = None


class InvoiceCustomField(BaseModel):
    """Custom field on the invoice."""

    name: Annotated[str, Field(description="The name of the custom field.")]
    value: Annotated[str, Field(description="The value of the custom field.")]


class InvoiceIssuer(BaseModel):
    """The connected account that issues the invoice."""

    account: Annotated[
        str | None,
        Field(
            description="The connected account being referenced when `type` is `account`."
        ),
    ] = None
    type: Annotated[
        Literal["account", "self"],
        Field(description="Type of the account referenced."),
    ]


class InvoiceRenderingOptions(BaseModel):
    """Options for invoice PDF rendering."""

    amount_tax_display: Annotated[
        str | None,
        Field(
            description="How line-item prices and amounts will be displayed with respect to tax on invoice PDFs."
        ),
    ] = None
    template: Annotated[
        str | None,
        Field(
            description="ID of the invoice rendering template to be used for the generated invoice."
        ),
    ] = None


class InvoiceCreationData(BaseModel):
    """Parameters passed when creating invoices for payment-mode Checkout Sessions."""

    account_tax_ids: Annotated[
        list[str] | None,
        Field(description="The account tax IDs associated with the invoice."),
    ] = None
    custom_fields: Annotated[
        list[InvoiceCustomField] | None,
        Field(description="Custom fields displayed on the invoice."),
    ] = None
    description: Annotated[
        str | None,
        Field(description="An arbitrary string attached to the object."),
    ] = None
    footer: Annotated[
        str | None,
        Field(description="Footer displayed on the invoice."),
    ] = None
    issuer: Annotated[
        InvoiceIssuer | None,
        Field(description="The connected account that issues the invoice."),
    ] = None
    metadata: Annotated[
        dict[str, Any] | None,
        Field(description="Set of key-value pairs that you can attach to the invoice."),
    ] = None
    rendering_options: Annotated[
        InvoiceRenderingOptions | None,
        Field(description="Options for invoice PDF rendering."),
    ] = None


class InvoiceCreation(BaseModel):
    """Details on the state of invoice creation for the Checkout Session."""

    enabled: Annotated[
        bool,
        Field(
            description="Whether invoice creation is enabled for the Checkout Session."
        ),
    ]
    invoice_data: Annotated[
        InvoiceCreationData,
        Field(
            description="Parameters passed when creating invoices for payment-mode Checkout Sessions."
        ),
    ]


class LineItemDiscount(BaseModel):
    """Discount applied to line item."""

    amount: Annotated[int, Field(description="The amount discounted.")]
    discount: Annotated[
        dict[str, Any],
        Field(description="The discount applied."),
    ]


class LineItemTax(BaseModel):
    """Tax applied to line item."""

    amount: Annotated[int, Field(description="Amount of tax applied for this rate.")]
    rate: Annotated[
        dict[str, Any],
        Field(description="The tax rate applied."),
    ]


class LineItemPrice(BaseModel):
    """Price used to generate the line item."""

    id: Annotated[str, Field(description="Unique identifier for the price.")]
    object: Annotated[Literal["price"], Field(description="Always 'price'.")]
    active: Annotated[
        bool, Field(description="Whether the price can be used for new purchases.")
    ]
    currency: Annotated[str, Field(description="Three-letter ISO currency code.")]
    unit_amount: Annotated[
        int | None,
        Field(description="Unit amount in cents."),
    ] = None


class LineItemData(BaseModel):
    """Details about each line item."""

    id: Annotated[str, Field(description="Unique identifier for the object.")]
    object: Annotated[Literal["line_item"], Field(description="Always 'line_item'.")]
    amount_discount: Annotated[
        int,
        Field(description="Total discount amount applied."),
    ]
    amount_subtotal: Annotated[
        int,
        Field(description="Total before any discounts or taxes are applied."),
    ]
    amount_tax: Annotated[
        int,
        Field(description="Total tax amount applied."),
    ]
    amount_total: Annotated[
        int,
        Field(description="Total after discounts and taxes."),
    ]
    currency: Annotated[str, Field(description="Three-letter ISO currency code.")]
    description: Annotated[
        str | None,
        Field(description="An arbitrary string attached to the object."),
    ] = None
    discounts: Annotated[
        list[LineItemDiscount] | None,
        Field(description="The discounts applied to the line item."),
    ] = None
    price: Annotated[
        LineItemPrice | None,
        Field(description="The price used to generate the line item."),
    ] = None
    quantity: Annotated[
        int | None,
        Field(description="The quantity of products being purchased."),
    ] = None
    taxes: Annotated[
        list[LineItemTax] | None,
        Field(description="The taxes applied to the line item."),
    ] = None


class LineItems(BaseModel):
    """Line items purchased by the customer."""

    object: Annotated[Literal["list"], Field(description="Always 'list'.")]
    data: Annotated[
        list[LineItemData],
        Field(description="Details about each object."),
    ]
    has_more: Annotated[
        bool,
        Field(
            description="True if this list has another page of items after this one."
        ),
    ]
    url: Annotated[
        str,
        Field(description="The URL where this list can be accessed."),
    ]


class TotalDetailsBreakdownDiscount(BaseModel):
    """Aggregated discount."""

    amount: Annotated[int, Field(description="The amount discounted.")]
    discount: Annotated[
        dict[str, Any],
        Field(description="The discount applied."),
    ]


class TotalDetailsBreakdownTax(BaseModel):
    """Aggregated tax."""

    amount: Annotated[int, Field(description="Amount of tax applied for this rate.")]
    rate: Annotated[
        dict[str, Any],
        Field(description="The tax rate applied."),
    ]


class TotalDetailsBreakdown(BaseModel):
    """Breakdown of individual tax and discount amounts."""

    discounts: Annotated[
        list[TotalDetailsBreakdownDiscount] | None,
        Field(description="The aggregated discounts."),
    ] = None
    taxes: Annotated[
        list[TotalDetailsBreakdownTax] | None,
        Field(description="The aggregated tax amounts by rate."),
    ] = None


class TotalDetails(BaseModel):
    """Tax and discount details for the computed total amount."""

    amount_discount: Annotated[
        int,
        Field(description="This is the sum of all the discounts."),
    ]
    amount_shipping: Annotated[
        int | None,
        Field(description="This is the sum of all the shipping amounts."),
    ] = None
    amount_tax: Annotated[
        int,
        Field(description="This is the sum of all the tax amounts."),
    ]
    breakdown: Annotated[
        TotalDetailsBreakdown | None,
        Field(description="Breakdown of individual tax and discount amounts."),
    ] = None


class CollectedInformationShippingDetails(BaseModel):
    """Shipping information collected."""

    address: Annotated[
        CustomerAddress | None,
        Field(description="Customer address."),
    ] = None
    name: Annotated[
        str,
        Field(description="Customer name."),
    ]


class CollectedInformation(BaseModel):
    """Information about the customer collected within the Checkout Session."""

    business_name: Annotated[
        str | None,
        Field(description="Customer's business name for this Checkout Session."),
    ] = None
    individual_name: Annotated[
        str | None,
        Field(description="Customer's individual name for this Checkout Session."),
    ] = None
    shipping_details: Annotated[
        CollectedInformationShippingDetails | None,
        Field(description="Shipping information for this Checkout Session."),
    ] = None


class CurrencyConversion(BaseModel):
    """Currency conversion details for Adaptive Pricing sessions."""

    amount_subtotal: Annotated[
        int,
        Field(
            description="Total of all items in source currency before discounts or taxes."
        ),
    ]
    amount_total: Annotated[
        int,
        Field(
            description="Total of all items in source currency after discounts and taxes."
        ),
    ]
    fx_rate: Annotated[
        str,
        Field(
            description="Exchange rate used to convert source currency amounts to customer currency amounts."
        ),
    ]
    source_currency: Annotated[
        str,
        Field(
            description="Creation currency of the CheckoutSession before localization."
        ),
    ]


class PaymentMethodConfigurationDetails(BaseModel):
    """Information about the payment method configuration used."""

    id: Annotated[
        str,
        Field(description="ID of the payment method configuration used."),
    ]
    parent: Annotated[
        str | None,
        Field(description="ID of the parent payment method configuration used."),
    ] = None


class Permissions(BaseModel):
    """Permissions for various actions on the CheckoutSession object."""

    update_shipping_details: Annotated[
        Literal["client_only", "server_only"] | None,
        Field(
            description="Determines which entity is allowed to update the shipping details."
        ),
    ] = None


class PresentmentDetails(BaseModel):
    """Currency presentation to the customer."""

    presentment_amount: Annotated[
        int,
        Field(
            description="Amount intended to be collected, denominated in `presentment_currency`."
        ),
    ]
    presentment_currency: Annotated[
        str,
        Field(description="Currency presented to the customer during payment."),
    ]


class SavedPaymentMethodOptions(BaseModel):
    """Controls saved payment method settings for the session."""

    allow_redisplay_filters: Annotated[
        list[Literal["always", "limited", "unspecified"]] | None,
        Field(
            description="Filter the set of saved payment methods presented to the customer."
        ),
    ] = None
    payment_method_remove: Annotated[
        Literal["disabled", "enabled"] | None,
        Field(description="Whether customers can remove their saved payment methods."),
    ] = None
    payment_method_save: Annotated[
        Literal["disabled", "enabled"] | None,
        Field(
            description="Whether customers can save their payment method for future use."
        ),
    ] = None


class AdaptivePricing(BaseModel):
    """Settings for price localization with Adaptive Pricing."""

    enabled: Annotated[
        bool,
        Field(description="Whether Adaptive Pricing is enabled for this session."),
    ]


class ShippingOption(BaseModel):
    """Shipping rate option applied to this Session."""

    shipping_amount: Annotated[
        int,
        Field(
            description="A non-negative integer in cents representing how much to charge."
        ),
    ]
    shipping_rate: Annotated[
        str,
        Field(description="The shipping rate."),
    ]


class CheckoutSession(BaseModel):
    """Complete Stripe Checkout Session object."""

    # Core identifiers and metadata
    id: Annotated[str, Field(description="Unique identifier for the object.")]
    object: Annotated[
        Literal["checkout.session"],
        Field(
            description="String representing the object's type. Always 'checkout.session'."
        ),
    ] = "checkout.session"
    livemode: Annotated[
        bool,
        Field(
            description="Has the value `true` if the object exists in live mode or the value `false` if the object exists in test mode."
        ),
    ]
    mode: Annotated[
        Literal["payment", "setup", "subscription"],
        Field(description="The mode of the Checkout Session."),
    ]

    # Timestamps
    created: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]
    expires_at: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(description="The timestamp at which the Checkout Session will expire."),
    ]

    # URLs and redirects
    success_url: Annotated[
        str | None,
        Field(
            description="The URL the customer will be directed to after the payment or subscription creation is successful."
        ),
    ] = None
    cancel_url: Annotated[
        str | None,
        Field(
            description="If set, Checkout displays a back button and customers will be directed to this URL if they decide to cancel payment and return to your website."
        ),
    ] = None
    return_url: Annotated[
        str | None,
        Field(
            description="Applies to Checkout Sessions with `ui_mode: embedded` or `ui_mode: custom`. The URL to redirect your customer back to after they authenticate or cancel their payment on the payment method's app or site."
        ),
    ] = None
    url: Annotated[
        str | None,
        Field(
            description="The URL to the Checkout Session. Applies to Checkout Sessions with `ui_mode: hosted`."
        ),
    ] = None
    client_secret: Annotated[
        str | None,
        Field(
            description="The client secret of your Checkout Session. Applies to Checkout Sessions with `ui_mode: embedded` or `ui_mode: custom`."
        ),
    ] = None

    # Customer information
    customer: Annotated[
        str | None,
        Field(
            description="The ID of the customer for this Session. For Checkout Sessions in `subscription` mode or Checkout Sessions with `customer_creation` set as `always` in `payment` mode, Checkout will create a new customer object based on information provided during the payment flow unless an existing customer was provided when the Session was created."
        ),
    ] = None
    customer_email: Annotated[
        str | None,
        Field(
            description="If provided, this value will be used when the Customer object is created. Use this parameter to prefill customer data if you already have an email on file."
        ),
    ] = None
    customer_account: Annotated[
        str | None, Field(description="The ID of the account for this Session.")
    ] = None
    customer_creation: Annotated[
        Literal["always", "if_required"] | None,
        Field(
            description="Configure whether a Checkout Session creates a Customer when the Checkout Session completes."
        ),
    ] = None
    customer_details: Annotated[
        CustomerDetails | None,
        Field(
            description="The customer details including the customer's tax exempt status and the customer's tax IDs."
        ),
    ] = None

    # Payment information
    payment_intent: Annotated[
        str | None,
        Field(
            description="The ID of the PaymentIntent for Checkout Sessions in `payment` mode."
        ),
    ] = None
    payment_status: Annotated[
        Literal["paid", "unpaid", "no_payment_required"],
        Field(
            description="The payment status of the Checkout Session, one of `paid`, `unpaid`, or `no_payment_required`."
        ),
    ]
    payment_link: Annotated[
        str | None,
        Field(description="The ID of the Payment Link that created this Session."),
    ] = None
    payment_method_collection: Annotated[
        Literal["always", "if_required"] | None,
        Field(
            description="Configure whether a Checkout Session should collect a payment method. Defaults to `always`."
        ),
    ] = None
    payment_method_types: Annotated[
        list[str] | None,
        Field(
            description="A list of the types of payment methods (e.g., 'card') this Checkout Session is allowed to accept."
        ),
    ] = None
    payment_method_options: Annotated[
        dict[str, Any] | None,
        Field(
            description="Payment-method-specific configuration for the PaymentIntent or SetupIntent of this CheckoutSession."
        ),
    ] = None  # TODO: Create PaymentMethodOptions schema
    excluded_payment_method_types: Annotated[
        list[str] | None,
        Field(
            description="A list of the types of payment methods that should be excluded from this Checkout Session."
        ),
    ] = None

    # Subscription and setup
    subscription: Annotated[
        str | None,
        Field(
            description="The ID of the Subscription for Checkout Sessions in `subscription` mode."
        ),
    ] = None
    setup_intent: Annotated[
        str | None,
        Field(
            description="The ID of the SetupIntent for Checkout Sessions in `setup` mode."
        ),
    ] = None

    # Session status and recovery
    status: Annotated[
        Literal["open", "complete", "expired"] | None,
        Field(
            description="The status of the Checkout Session, one of `open`, `complete`, or `expired`."
        ),
    ] = None
    recovered_from: Annotated[
        str | None,
        Field(
            description="The ID of the original expired Checkout Session that triggered the recovery flow."
        ),
    ] = None
    after_expiration: Annotated[
        AfterExpiration | None,
        Field(
            description="When set, provides configuration for actions to take if this Checkout Session expires."
        ),
    ] = None

    # Currency and amounts
    currency: Annotated[
        str | None,
        Field(
            description="Three-letter ISO currency code, in lowercase. Must be a supported currency."
        ),
    ] = None
    amount_subtotal: Annotated[
        int | None,
        Field(description="Total of all items before discounts or taxes are applied."),
    ] = None
    amount_total: Annotated[
        int | None,
        Field(description="Total of all items after discounts and taxes are applied."),
    ] = None

    # Discounts and promotion codes
    allow_promotion_codes: Annotated[
        bool | None,
        Field(description="Enables user redeemable promotion codes."),
    ] = None
    discounts: Annotated[
        list[Discount] | None,
        Field(
            description="List of coupons and promotion codes attached to the Checkout Session."
        ),
    ] = None

    # Tax and automation
    automatic_tax: Annotated[
        AutomaticTax,
        Field(
            description="Details on the state of automatic tax for the session, including the status of the latest tax calculation."
        ),
    ]
    billing_address_collection: Annotated[
        Literal["auto", "required"] | None,
        Field(
            description="Describes whether Checkout should collect the customer's billing address. Defaults to `auto`."
        ),
    ] = None

    # Shipping information
    shipping_address_collection: Annotated[
        ShippingAddressCollection | None,
        Field(
            description="When set, provides configuration for Checkout to collect a shipping address from a customer."
        ),
    ] = None
    shipping_cost: Annotated[
        ShippingCost | None,
        Field(
            description="The details of the customer cost of shipping, including the customer chosen ShippingRate."
        ),
    ] = None
    shipping_options: Annotated[
        list[ShippingOption] | None,
        Field(description="The shipping rate options applied to this Session."),
    ] = None

    # Custom fields and text
    custom_fields: Annotated[
        list[CustomField] | None,
        Field(
            description="Collect additional information from your customer using custom fields. Up to 3 fields are supported."
        ),
    ] = None
    custom_text: Annotated[
        CustomText | None,
        Field(
            description="Display additional text for your customers using custom text."
        ),
    ] = None

    # Metadata and reference
    metadata: Annotated[
        dict[str, Any] | None,
        Field(
            description="Set of key-value pairs that you can attach to an object. Useful for storing additional information about the object in a structured format."
        ),
    ] = None
    client_reference_id: Annotated[
        str | None,
        Field(
            description="A unique string to reference the Checkout Session. This can be a customer ID, a cart ID, or similar, and can be used to reconcile the Session with your internal systems."
        ),
    ] = None

    # Consent and collection
    consent: Annotated[
        ConsentResult | None,
        Field(description="Results of `consent_collection` for this session."),
    ] = None
    consent_collection: Annotated[
        ConsentCollection | None,
        Field(
            description="When set, provides configuration for the Checkout Session to gather active consent from customers."
        ),
    ] = None

    # Presentation and UI
    ui_mode: Annotated[
        Literal["custom", "embedded", "hosted"] | None,
        Field(description="The UI mode of the Session. Defaults to `hosted`."),
    ] = None
    locale: Annotated[
        str | None,
        Field(
            description="The IETF language tag of the locale Checkout is displayed in. If blank or `auto`, the browser's locale is used."
        ),
    ] = None
    redirect_on_completion: Annotated[
        Literal["always", "if_required", "never"] | None,
        Field(
            description="This parameter applies to `ui_mode: embedded`. Defaults to `always`."
        ),
    ] = None
    submit_type: Annotated[
        Literal["auto", "book", "donate", "pay", "subscribe"] | None,
        Field(
            description="Describes the type of transaction being performed by Checkout in order to customize relevant text on the page, such as the submit button."
        ),
    ] = None

    # Branding and presentation
    branding_settings: Annotated[
        BrandingSettings | None,
        Field(description="Details on the state of branding settings for the session."),
    ] = None
    wallet_options: Annotated[
        WalletOptions | None,
        Field(description="Wallet-specific configuration for this Checkout Session."),
    ] = None

    # Collection configuration
    phone_number_collection: Annotated[
        PhoneNumberCollection | None,
        Field(
            description="Details on the state of phone number collection for the session."
        ),
    ] = None
    name_collection: Annotated[
        NameCollection | None,
        Field(description="Details on the state of name collection for the session."),
    ] = None
    tax_id_collection: Annotated[
        TaxIDCollection | None,
        Field(description="Details on the state of tax ID collection for the session."),
    ] = None

    # Invoice and tax details
    invoice: Annotated[
        str | None,
        Field(
            description="ID of the invoice created by the Checkout Session, if it exists."
        ),
    ] = None
    invoice_creation: Annotated[
        InvoiceCreation | None,
        Field(
            description="Details on the state of invoice creation for the Checkout Session."
        ),
    ] = None

    # Line items and totals
    line_items: Annotated[
        LineItems | None,
        Field(description="The line items purchased by the customer."),
    ] = None
    total_details: Annotated[
        TotalDetails | None,
        Field(description="Tax and discount details for the computed total amount."),
    ] = None

    # Additional fields
    collected_information: Annotated[
        CollectedInformation | None,
        Field(
            description="Information about the customer collected within the Checkout Session."
        ),
    ] = None
    currency_conversion: Annotated[
        CurrencyConversion | None,
        Field(
            description="Currency conversion details for Adaptive Pricing sessions created before 2025-03-31."
        ),
    ] = None
    origin_context: Annotated[
        Literal["mobile_app", "web"] | None,
        Field(
            description="Where the user is coming from. This informs the optimizations that are applied to the session."
        ),
    ] = None
    payment_method_configuration_details: Annotated[
        PaymentMethodConfigurationDetails | None,
        Field(
            description="Information about the payment method configuration used for this Checkout session if using dynamic payment methods."
        ),
    ] = None
    permissions: Annotated[
        Permissions | None,
        Field(
            description="This property is used to set up permissions for various actions (e.g., update) on the CheckoutSession object."
        ),
    ] = None
    presentment_details: Annotated[
        PresentmentDetails | None,
        Field(
            description="A hash containing information about the currency presentation to the customer, including the displayed currency and amount used for conversion from the integration currency."
        ),
    ] = None
    saved_payment_method_options: Annotated[
        SavedPaymentMethodOptions | None,
        Field(
            description="Controls saved payment method settings for the session. Only available in `payment` and `subscription` mode."
        ),
    ] = None
    adaptive_pricing: Annotated[
        AdaptivePricing | None,
        Field(description="Settings for price localization with Adaptive Pricing."),
    ] = None
    optional_items: Annotated[
        list[dict[str, Any]] | None,
        Field(description="The optional items presented to the customer at checkout."),
    ] = None


class DeleteResponse(BaseModel):
    id: str
    deleted: bool


class CreatedParams(BaseModel):
    gt: int | None = None
    gte: int | None = None
    lt: int | None = None
    lte: int | None = None


class ShippingAddress(BaseModel):
    """Shipping address for payment intent."""

    line1: Annotated[
        str,
        Field(
            description="Address line 1, such as the street, PO Box, or company name."
        ),
    ]
    city: Annotated[
        str | None, Field(description="City, district, suburb, town, or village.")
    ] = None
    country: Annotated[
        str | None, Field(description="Two-letter country code (ISO 3166-1 alpha-2).")
    ] = None
    line2: Annotated[
        str | None,
        Field(
            description="Address line 2, such as the apartment, suite, unit, or building."
        ),
    ] = None
    postal_code: Annotated[str | None, Field(description="ZIP or postal code.")] = None
    state: Annotated[
        str | None, Field(description="State, county, province, or region.")
    ] = None


class ShippingInfo(BaseModel):
    """Shipping information for this payment."""

    name: Annotated[str, Field(description="Recipient name.")]
    address: Annotated[ShippingAddress, Field(description="Shipping address.")]
    carrier: Annotated[
        str | None,
        Field(
            description="The delivery service that shipped a physical product, such as Fedex, UPS, USPS, etc."
        ),
    ] = None
    phone: Annotated[
        str | None, Field(description="Recipient phone (including extension).")
    ] = None
    tracking_number: Annotated[
        str | None,
        Field(
            description="The tracking number for a physical product, obtained from the delivery service."
        ),
    ] = None


class TransferData(BaseModel):
    """Parameters for automatically creating a Transfer when the payment succeeds."""

    destination: Annotated[
        str, Field(description="The Stripe account ID for the destination account.")
    ]
    amount: Annotated[
        int | None,
        Field(
            description="The amount that will be transferred automatically when a charge succeeds."
        ),
    ] = None


class PaymentIntentData(BaseModel):
    """A subset of parameters to be passed to PaymentIntent creation for Checkout Sessions in payment mode."""

    application_fee_amount: Annotated[
        int | None,
        Field(
            description="Connect only. The amount of the application fee (if any) that will be requested to be applied to the payment."
        ),
    ] = None
    capture_method: Annotated[
        Literal["automatic", "automatic_async", "manual"] | None,
        Field(
            description="Controls when the funds will be captured from the customer's account."
        ),
    ] = None
    description: Annotated[
        str | None,
        Field(
            description="An arbitrary string attached to the object. Often useful for displaying to users."
        ),
    ] = None
    metadata: Annotated[
        dict[str, Any] | None,
        Field(description="Set of key-value pairs that you can attach to an object."),
    ] = None
    on_behalf_of: Annotated[
        str | None,
        Field(
            description="Connect only. The Stripe account ID for which these funds are intended."
        ),
    ] = None
    receipt_email: Annotated[
        str | None,
        Field(
            description="Email address that the receipt for the resulting payment will be sent to."
        ),
    ] = None
    setup_future_usage: Annotated[
        Literal["off_session", "on_session"] | None,
        Field(
            description="Indicates that you intend to make future payments with the payment method collected by this Checkout Session."
        ),
    ] = None
    shipping: Annotated[
        ShippingInfo | dict[str, Any] | None,
        Field(description="Shipping information for this payment."),
    ] = None
    statement_descriptor: Annotated[
        str | None,
        Field(
            description="Text that appears on the customer's statement as the statement descriptor for a non-card charge."
        ),
    ] = None
    statement_descriptor_suffix: Annotated[
        str | None,
        Field(
            description="Provides information about a card charge. Concatenated to the account's statement descriptor prefix."
        ),
    ] = None
    transfer_data: Annotated[
        TransferData | dict[str, Any] | None,
        Field(
            description="Connect only. The parameters used to automatically create a Transfer when the payment succeeds."
        ),
    ] = None
    transfer_group: Annotated[
        str | None,
        Field(
            description="Connect only. A string that identifies the resulting payment as part of a group."
        ),
    ] = None


class BillingModeFlexible(BaseModel):
    """Configure behavior for flexible billing mode."""

    proration_discounts: Annotated[
        Literal["included", "itemized"] | None,
        Field(
            description="Controls how invoices and invoice items display proration amounts and discount amounts."
        ),
    ] = None


class BillingMode(BaseModel):
    """Controls how prorations and invoices for subscriptions are calculated and orchestrated."""

    type: Annotated[
        Literal["classic", "flexible"],
        Field(
            description="Controls the calculation and orchestration of prorations and invoices for subscriptions."
        ),
    ]
    flexible: Annotated[
        BillingModeFlexible | dict[str, Any] | None,
        Field(description="Configure behavior for flexible billing mode."),
    ] = None


class InvoiceSettingsIssuer(BaseModel):
    """The connected account that issues the invoice."""

    type: Annotated[
        Literal["account", "self"],
        Field(description="Type of the account referenced in the request."),
    ]
    account: Annotated[
        str | None,
        Field(
            description="The connected account being referenced when type is account."
        ),
    ] = None


class InvoiceSettings(BaseModel):
    """All invoices will be billed using the specified settings."""

    issuer: Annotated[
        InvoiceSettingsIssuer | dict[str, Any] | None,
        Field(description="The connected account that issues the invoice."),
    ] = None


class SubscriptionTransferData(BaseModel):
    """Parameters for transferring subscription invoice funds to a connected account."""

    destination: Annotated[
        str, Field(description="ID of an existing, connected Stripe account.")
    ]
    amount_percent: Annotated[
        float | None,
        Field(
            description="A non-negative decimal between 0 and 100, with at most two decimal places."
        ),
    ] = None


class TrialEndBehavior(BaseModel):
    """Defines how the subscription should behave when the trial ends."""

    missing_payment_method: Annotated[
        Literal["cancel", "create_invoice", "pause"],
        Field(
            description="Indicates how the subscription should change when the trial ends if the user did not provide a payment method."
        ),
    ]


class TrialSettings(BaseModel):
    """Settings related to subscription trials."""

    end_behavior: Annotated[
        TrialEndBehavior | dict[str, Any],
        Field(
            description="Defines how the subscription should behave when the trial ends."
        ),
    ]


class SubscriptionData(BaseModel):
    """A subset of parameters to be passed to subscription creation for Checkout Sessions in subscription mode."""

    application_fee_percent: Annotated[
        float | None,
        Field(
            description="Connect only. A non-negative decimal between 0 and 100, with at most two decimal places."
        ),
    ] = None
    billing_cycle_anchor: Annotated[
        int | None,
        Field(
            description="A future timestamp to anchor the subscription's billing cycle for new subscriptions."
        ),
    ] = None
    billing_mode: Annotated[
        BillingMode | dict[str, Any] | None,
        Field(
            description="Controls how prorations and invoices for subscriptions are calculated and orchestrated."
        ),
    ] = None
    default_tax_rates: Annotated[
        list[str] | None,
        Field(
            description="The tax rates that will apply to any subscription item that does not have tax_rates set."
        ),
    ] = None
    description: Annotated[
        str | None,
        Field(
            description="The subscription's description, meant to be displayable to the customer. Maximum length is 500 characters."
        ),
    ] = None
    invoice_settings: Annotated[
        InvoiceSettings | dict[str, Any] | None,
        Field(description="All invoices will be billed using the specified settings."),
    ] = None
    metadata: Annotated[
        dict[str, Any] | None,
        Field(description="Set of key-value pairs that you can attach to an object."),
    ] = None
    on_behalf_of: Annotated[
        str | None,
        Field(
            description="The account on behalf of which to charge, for each of the subscription's invoices."
        ),
    ] = None
    proration_behavior: Annotated[
        Literal["create_prorations", "none"] | None,
        Field(
            description="Determines how to handle prorations resulting from the billing_cycle_anchor."
        ),
    ] = None
    transfer_data: Annotated[
        SubscriptionTransferData | dict[str, Any] | None,
        Field(
            description="Connect only. If specified, the funds from the subscription's invoices will be transferred to the destination."
        ),
    ] = None
    trial_end: Annotated[
        int | None,
        Field(
            description="Unix timestamp representing the end of the trial period the customer will get before being charged for the first time."
        ),
    ] = None
    trial_period_days: Annotated[
        int | None,
        Field(
            description="Integer representing the number of trial period days before the customer is charged for the first time."
        ),
    ] = None
    trial_settings: Annotated[
        TrialSettings | dict[str, Any] | None,
        Field(description="Settings related to subscription trials."),
    ] = None


class AutomaticTaxLiability(BaseModel):
    """The account that's liable for tax."""

    account: Annotated[
        str | None,
        Field(
            description="The connected account being referenced when `type` is `account`."
        ),
    ] = None
    type: Annotated[
        Literal["account", "self"],
        Field(description="Type of the account referenced."),
    ]


class SubscriptionAutomaticTax(BaseModel):
    """Automatic tax settings for this subscription."""

    disabled_reason: Annotated[
        Literal["requires_location_inputs"] | None,
        Field(description="If Stripe disabled automatic tax, this enum describes why."),
    ] = None
    enabled: Annotated[
        bool,
        Field(
            description="Whether Stripe automatically computes tax on this subscription."
        ),
    ]
    liability: Annotated[
        AutomaticTaxLiability | None,
        Field(
            description="The account that's liable for tax. If set, the business address and tax registrations required to perform the tax calculation are loaded from this account."
        ),
    ] = None


class BillingCycleAnchorConfig(BaseModel):
    """The fixed values used to calculate the billing_cycle_anchor."""

    day_of_month: Annotated[
        int,
        Field(description="The day of the month of the billing_cycle_anchor."),
    ]
    hour: Annotated[
        int | None,
        Field(description="The hour of the day of the billing_cycle_anchor."),
    ] = None
    minute: Annotated[
        int | None,
        Field(description="The minute of the hour of the billing_cycle_anchor."),
    ] = None
    month: Annotated[
        int | None,
        Field(description="The month to start full cycle billing periods."),
    ] = None
    second: Annotated[
        int | None,
        Field(description="The second of the minute of the billing_cycle_anchor."),
    ] = None


class SubscriptionBillingMode(BaseModel):
    """Controls how prorations and invoices for subscriptions are calculated and orchestrated."""

    flexible: Annotated[
        BillingModeFlexible | None,
        Field(description="Configure behavior for flexible billing mode."),
    ] = None
    type: Annotated[
        Literal["classic", "flexible"],
        Field(
            description="Controls how prorations and invoices for subscriptions are calculated and orchestrated."
        ),
    ]
    updated_at: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(description="Details on when the current billing_mode was adopted."),
    ] = None


class BillingThresholds(BaseModel):
    """Define thresholds at which an invoice will be sent, and the subscription advanced to a new billing period."""

    amount_gte: Annotated[
        int | None,
        Field(
            description="Monetary threshold that triggers the subscription to create an invoice"
        ),
    ] = None
    reset_billing_cycle_anchor: Annotated[
        bool | None,
        Field(
            description="Indicates if the `billing_cycle_anchor` should be reset when a threshold is reached."
        ),
    ] = None


class CancellationDetails(BaseModel):
    """Details about why this subscription was cancelled."""

    comment: Annotated[
        str | None,
        Field(
            description="Additional comments about why the user canceled the subscription, if the subscription was canceled explicitly by the user."
        ),
    ] = None
    feedback: Annotated[
        Literal[
            "customer_service",
            "low_quality",
            "missing_features",
            "other",
            "switched_service",
            "too_complex",
            "too_expensive",
            "unused",
        ]
        | None,
        Field(
            description="The customer submitted reason for why they canceled, if the subscription was canceled explicitly by the user."
        ),
    ] = None
    reason: Annotated[
        Literal["cancellation_requested", "payment_disputed", "payment_failed"] | None,
        Field(description="Why this subscription was canceled."),
    ] = None


class TaxRateFlatAmount(BaseModel):
    """The amount and currency of the flat tax rate."""

    amount: Annotated[
        int,
        Field(
            description="Amount of the tax when the `rate_type` is `flat_amount`. This positive integer represents how much to charge in the smallest currency unit."
        ),
    ]
    currency: Annotated[
        str,
        Field(description="Three-letter ISO currency code, in lowercase."),
    ]


class TaxRate(BaseModel):
    """Tax rate object."""

    id: Annotated[str, Field(description="Unique identifier for the object.")]
    object: Annotated[
        Literal["tax_rate"],
        Field(description="String representing the object's type."),
    ] = "tax_rate"
    active: Annotated[
        bool,
        Field(
            description="Defaults to `true`. When set to `false`, this tax rate cannot be used with new applications or Checkout Sessions."
        ),
    ]
    country: Annotated[
        str | None,
        Field(description="Two-letter country code (ISO 3166-1 alpha-2)."),
    ] = None
    created: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]
    description: Annotated[
        str | None,
        Field(
            description="An arbitrary string attached to the tax rate for your internal use only."
        ),
    ] = None
    display_name: Annotated[
        str,
        Field(
            description="The display name of the tax rates as it will appear to your customer on their receipt email, PDF, and the hosted invoice page."
        ),
    ]
    effective_percentage: Annotated[
        float | None,
        Field(
            description="Actual/effective tax rate percentage out of 100. For tax calculations with automatic_tax[enabled]=true, this percentage reflects the rate actually used to calculate tax."
        ),
    ] = None
    flat_amount: Annotated[
        TaxRateFlatAmount | None,
        Field(
            description="The amount of the tax rate when the `rate_type` is `flat_amount`."
        ),
    ] = None
    inclusive: Annotated[
        bool,
        Field(description="This specifies if the tax rate is inclusive or exclusive."),
    ]
    jurisdiction: Annotated[
        str | None,
        Field(
            description="The jurisdiction for the tax rate. You can use this label field for tax reporting purposes."
        ),
    ] = None
    jurisdiction_level: Annotated[
        Literal["city", "country", "county", "district", "multiple", "state"] | None,
        Field(
            description="The level of the jurisdiction that imposes this tax rate. Will be `null` for manually defined tax rates."
        ),
    ] = None
    livemode: Annotated[
        bool,
        Field(
            description="Has the value `true` if the object exists in live mode or the value `false` if the object exists in test mode."
        ),
    ]
    metadata: Annotated[
        dict[str, Any] | None,
        Field(
            description="Set of key-value pairs that you can attach to an object. This can be useful for storing additional information about the object in a structured format."
        ),
    ] = None
    percentage: Annotated[
        float,
        Field(
            description="Tax rate percentage out of 100. For tax calculations with automatic_tax[enabled]=true, this percentage includes the statutory tax rate of non-taxable jurisdictions."
        ),
    ]
    rate_type: Annotated[
        Literal["flat_amount", "percentage"] | None,
        Field(
            description="Indicates the type of tax rate applied to the taxable amount. This value can be `null` when no tax applies to the location."
        ),
    ] = None
    state: Annotated[
        str | None,
        Field(
            description="ISO 3166-2 subdivision code, without country prefix. For example, 'NY' for New York, United States."
        ),
    ] = None
    tax_type: Annotated[
        Literal[
            "amusement_tax",
            "communications_tax",
            "gst",
            "hst",
            "igst",
            "jct",
            "lease_tax",
            "pst",
            "qst",
            "retail_delivery_fee",
            "rst",
            "sales_tax",
            "service_tax",
            "vat",
        ]
        | None,
        Field(description="The high-level tax type, such as `vat` or `sales_tax`."),
    ] = None


class SubscriptionInvoiceSettings(BaseModel):
    """All invoices will be billed using the specified settings."""

    account_tax_ids: Annotated[
        list[str] | None,
        Field(
            description="The account tax IDs associated with the subscription. Will be set on invoices generated by the subscription."
        ),
    ] = None
    issuer: Annotated[
        InvoiceSettingsIssuer,
        Field(
            description="The connected account that issues the invoice. The invoice is presented with the branding and support information of the specified account."
        ),
    ]


class SubscriptionItemBillingThresholds(BaseModel):
    """Define thresholds at which an invoice will be sent, and the related subscription advanced to a new billing period."""

    usage_gte: Annotated[
        int | None,
        Field(
            description="Usage threshold that triggers the subscription to create an invoice"
        ),
    ] = None


class SubscriptionItemPrice(BaseModel):
    """The price the customer is subscribed to."""

    id: Annotated[str, Field(description="Unique identifier for the object.")]
    object: Annotated[
        Literal["price"],
        Field(description="String representing the object's type."),
    ] = "price"
    active: Annotated[
        bool,
        Field(description="Whether the price can be used for new purchases."),
    ]
    billing_scheme: Annotated[
        Literal["per_unit", "tiered"],
        Field(
            description="Describes how to compute the price per period. Either `per_unit` or `tiered`."
        ),
    ]
    created: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]
    currency: Annotated[
        str,
        Field(
            description="Three-letter ISO currency code, in lowercase. Must be a supported currency."
        ),
    ]
    currency_options: Annotated[
        dict[str, CurrencyOptions] | None,
        Field(
            description="Prices defined in each available currency option. Each key must be a three-letter ISO currency code and a supported currency."
        ),
    ] = None
    custom_unit_amount: Annotated[
        CustomUnitAmount | None,
        Field(
            description="When set, provides configuration for the amount to be adjusted by the customer during Checkout Sessions and Payment Links."
        ),
    ] = None
    livemode: Annotated[
        bool,
        Field(
            description="Has the value `true` if the object exists in live mode or the value `false` if the object exists in test mode."
        ),
    ]
    lookup_key: Annotated[
        str | None,
        Field(
            description="A lookup key used to retrieve prices dynamically from a static string. This may be up to 200 characters."
        ),
    ] = None
    metadata: Annotated[
        dict[str, Any],
        Field(
            description="Set of key-value pairs that you can attach to an object. This can be useful for storing additional information about the object in a structured format."
        ),
    ] = {}
    nickname: Annotated[
        str | None,
        Field(description="A brief description of the price, hidden from customers."),
    ] = None
    product: Annotated[
        str,
        Field(description="The ID of the product this price is associated with."),
    ]
    recurring: Annotated[
        Recurring | None,
        Field(
            description="The recurring components of a price such as `interval` and `usage_type`."
        ),
    ] = None
    tax_behavior: Annotated[
        Literal["inclusive", "exclusive", "unspecified"] | None,
        Field(
            description="Specifies whether the price is considered inclusive of taxes or exclusive of taxes."
        ),
    ] = None
    tiers: Annotated[
        list[Tier] | None,
        Field(
            description="Each element represents a pricing tier. This parameter requires `billing_scheme` to be set to `tiered`."
        ),
    ] = None
    tiers_mode: Annotated[
        Literal["graduated", "volume"] | None,
        Field(
            description="Defines if the tiering price should be `graduated` or `volume` based."
        ),
    ] = None
    transform_quantity: Annotated[
        TransformQuantity | None,
        Field(
            description="Apply a transformation to the reported usage or set quantity before computing the amount billed. Cannot be combined with `tiers`."
        ),
    ] = None
    type: Annotated[
        Literal["one_time", "recurring"],
        Field(
            description="One of `one_time` or `recurring` depending on whether the price is for a one-time purchase or a recurring (subscription) purchase."
        ),
    ]
    unit_amount: Annotated[
        int | None,
        Field(
            description="The unit amount in cents to be charged, represented as a whole integer if possible. Only set if `billing_scheme=per_unit`."
        ),
    ] = None
    unit_amount_decimal: Annotated[
        Decimal | None,
        Field(
            description="The unit amount in cents to be charged, represented as a decimal string with at most 12 decimal places. Only set if `billing_scheme=per_unit`."
        ),
    ] = None


class SubscriptionItem(BaseModel):
    """Details about each subscription item."""

    id: Annotated[str, Field(description="Unique identifier for the object.")]
    object: Annotated[
        Literal["subscription_item"],
        Field(description="String representing the object's type."),
    ] = "subscription_item"
    billing_thresholds: Annotated[
        SubscriptionItemBillingThresholds | None,
        Field(
            description="Define thresholds at which an invoice will be sent, and the related subscription advanced to a new billing period"
        ),
    ] = None
    created: Annotated[
        int,
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]
    current_period_end: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="The end time of this subscription item's current billing period."
        ),
    ]
    current_period_start: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="The start time of this subscription item's current billing period."
        ),
    ]
    discounts: Annotated[
        list[str],
        Field(
            description="The discounts applied to the subscription item. Subscription item discounts are applied before subscription discounts. Use `expand[]=discounts` to expand each discount."
        ),
    ] = []
    metadata: Annotated[
        dict[str, Any],
        Field(
            description="Set of key-value pairs that you can attach to an object. This can be useful for storing additional information about the object in a structured format."
        ),
    ] = {}
    price: Annotated[
        SubscriptionItemPrice,
        Field(description="The price the customer is subscribed to."),
    ]
    quantity: Annotated[
        int | None,
        Field(
            description="The quantity of the plan to which the customer should be subscribed."
        ),
    ] = None
    subscription: Annotated[
        str,
        Field(description="The `subscription` this `subscription_item` belongs to."),
    ]
    tax_rates: Annotated[
        list[TaxRate] | None,
        Field(
            description="The tax rates which apply to this `subscription_item`. When set, the `default_tax_rates` on the subscription do not apply to this `subscription_item`."
        ),
    ] = None


class SubscriptionItems(BaseModel):
    """List of subscription items, each with an attached price."""

    object: Annotated[
        Literal["list"],
        Field(
            description="String representing the object's type. Always has the value `list`."
        ),
    ] = "list"
    data: Annotated[
        list[SubscriptionItem],
        Field(description="Details about each object."),
    ]
    has_more: Annotated[
        bool,
        Field(
            description="True if this list has another page of items after this one that can be fetched."
        ),
    ]
    url: Annotated[
        str,
        Field(description="The URL where this list can be accessed."),
    ]


class PauseCollection(BaseModel):
    """If specified, payment collection for this subscription will be paused."""

    behavior: Annotated[
        Literal["keep_as_draft", "mark_uncollectible", "void"],
        Field(
            description="The payment collection behavior for this subscription while paused. One of `keep_as_draft`, `mark_uncollectible`, or `void`."
        ),
    ]
    resumes_at: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="The time after which the subscription will resume collecting payments."
        ),
    ] = None


class AcssDebitMandateOptions(BaseModel):
    """Additional fields for Mandate creation."""

    transaction_type: Annotated[
        Literal["business", "personal"] | None,
        Field(description="Transaction type of the mandate."),
    ] = None


class AcssDebitPaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the Canadian pre-authorized debit payment method options to pass to invoices created by the subscription."""

    mandate_options: Annotated[
        AcssDebitMandateOptions | None,
        Field(description="Additional fields for Mandate creation"),
    ] = None
    verification_method: Annotated[
        Literal["automatic", "instant", "microdeposits"] | None,
        Field(description="Bank account verification method."),
    ] = None


class BancontactPaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the Bancontact payment method options to pass to invoices created by the subscription."""

    preferred_language: Annotated[
        Literal["de", "en", "fr", "nl"],
        Field(
            description="Preferred language of the Bancontact authorization page that the customer is redirected to."
        ),
    ]


class CardMandateOptions(BaseModel):
    """Configuration options for setting up an eMandate for cards issued in India."""

    amount: Annotated[
        int | None,
        Field(description="Amount to be charged for future payments."),
    ] = None
    amount_type: Annotated[
        Literal["fixed", "maximum"] | None,
        Field(
            description="One of `fixed` or `maximum`. If `fixed`, the `amount` param refers to the exact amount to be charged in future payments. If `maximum`, the amount charged can be up to the value passed for the `amount` param."
        ),
    ] = None
    description: Annotated[
        str | None,
        Field(
            description="A description of the mandate or subscription that is meant to be displayed to the customer. The maximum length is 200 characters."
        ),
    ] = None


class CardPaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the Card payment method options to pass to invoices created by the subscription."""

    mandate_options: Annotated[
        CardMandateOptions | None,
        Field(
            description="Configuration options for setting up an eMandate for cards issued in India."
        ),
    ] = None
    network: Annotated[
        Literal[
            "amex",
            "cartes_bancaires",
            "diners",
            "discover",
            "eftpos_au",
            "girocard",
            "interac",
            "jcb",
            "link",
            "mastercard",
            "unionpay",
            "unknown",
            "visa",
        ]
        | None,
        Field(
            description="Selected network to process this Subscription on. Depends on the available networks of the card attached to the Subscription. Can be only set confirm-time."
        ),
    ] = None
    request_three_d_secure: Annotated[
        Literal["any", "automatic", "challenge"] | None,
        Field(
            description="We strongly recommend that you rely on our SCA Engine to automatically prompt your customers for authentication based on risk level and other requirements. However, if you wish to request 3D Secure based on logic from your own fraud engine, provide this option."
        ),
    ] = None


class EuBankTransferOptions(BaseModel):
    """Configuration for eu_bank_transfer funding type."""

    country: Annotated[
        Literal["BE", "DE", "ES", "FR", "IE", "NL"],
        Field(
            description="The desired country code of the bank account information. Permitted values include: `BE`, `DE`, `ES`, `FR`, `IE`, or `NL`."
        ),
    ]


class BankTransferOptions(BaseModel):
    """Configuration for the bank transfer funding type, if the `funding_type` is set to `bank_transfer`."""

    eu_bank_transfer: Annotated[
        EuBankTransferOptions | None,
        Field(description="Configuration for eu_bank_transfer funding type."),
    ] = None
    type: Annotated[
        Literal[
            "eu_bank_transfer",
            "gb_bank_transfer",
            "jp_bank_transfer",
            "mx_bank_transfer",
            "us_bank_transfer",
        ]
        | None,
        Field(
            description="The bank transfer type that can be used for funding. Permitted values include: `eu_bank_transfer`, `gb_bank_transfer`, `jp_bank_transfer`, `mx_bank_transfer`, or `us_bank_transfer`."
        ),
    ] = None


class CustomerBalancePaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the Bank transfer payment method options to pass to invoices created by the subscription."""

    bank_transfer: Annotated[
        BankTransferOptions | None,
        Field(
            description="Configuration for the bank transfer funding type, if the `funding_type` is set to `bank_transfer`."
        ),
    ] = None
    funding_type: Annotated[
        Literal["bank_transfer"] | None,
        Field(
            description="The funding method type to be used when there are not enough funds in the customer balance. Permitted values include: `bank_transfer`."
        ),
    ] = None


class KonbiniPaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the Konbini payment method options to pass to invoices created by the subscription."""

    pass  # No specific fields documented


class PaytoMandateOptions(BaseModel):
    """Additional fields for Mandate creation."""

    amount: Annotated[
        int | None,
        Field(
            description="The maximum amount that can be collected in a single invoice. If you don't specify a maximum, then there is no limit."
        ),
    ] = None
    amount_type: Annotated[
        Literal["fixed", "maximum"] | None,
        Field(description="Only `maximum` is supported."),
    ] = None
    purpose: Annotated[
        Literal[
            "dependant_support",
            "government",
            "loan",
            "mortgage",
            "other",
            "pension",
            "personal",
            "retail",
            "salary",
            "tax",
            "utility",
        ]
        | None,
        Field(
            description="The purpose for which payments are made. Has a default value based on your merchant category code."
        ),
    ] = None


class PaytoPaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the PayTo payment method options to pass to invoices created by the subscription."""

    mandate_options: Annotated[
        PaytoMandateOptions | None,
        Field(description="Additional fields for Mandate creation."),
    ] = None


class SepaDebitPaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the SEPA Direct Debit payment method options to pass to invoices created by the subscription."""

    pass  # No specific fields documented


class FinancialConnectionsFilters(BaseModel):
    """Filter the list of accounts that are allowed to be linked."""

    account_subcategories: Annotated[
        list[Literal["checking", "savings"]] | None,
        Field(
            description="The account subcategories to use to filter for possible accounts to link. Valid subcategories are `checking` and `savings`."
        ),
    ] = None


class FinancialConnections(BaseModel):
    """Additional fields for Financial Connections Session creation."""

    filters: Annotated[
        FinancialConnectionsFilters | None,
        Field(description="Filter the list of accounts that are allowed to be linked."),
    ] = None
    permissions: Annotated[
        list[Literal["balances", "ownership", "payment_method", "transactions"]] | None,
        Field(
            description="The list of permissions to request. The `payment_method` permission must be included."
        ),
    ] = None
    prefetch: Annotated[
        list[Literal["balances", "ownership", "transactions"]] | None,
        Field(
            description="Data features requested to be retrieved upon account creation."
        ),
    ] = None


class UsBankAccountPaymentMethodOptions(BaseModel):
    """This sub-hash contains details about the ACH direct debit payment method options to pass to invoices created by the subscription."""

    financial_connections: Annotated[
        FinancialConnections | None,
        Field(
            description="Additional fields for Financial Connections Session creation"
        ),
    ] = None
    verification_method: Annotated[
        Literal["automatic", "instant", "microdeposits"] | None,
        Field(description="Bank account verification method."),
    ] = None


class PaymentMethodOptions(BaseModel):
    """Payment-method-specific configuration to provide to invoices created by the subscription."""

    acss_debit: Annotated[
        AcssDebitPaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the Canadian pre-authorized debit payment method options to pass to invoices created by the subscription."
        ),
    ] = None
    bancontact: Annotated[
        BancontactPaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the Bancontact payment method options to pass to invoices created by the subscription."
        ),
    ] = None
    card: Annotated[
        CardPaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the Card payment method options to pass to invoices created by the subscription."
        ),
    ] = None
    customer_balance: Annotated[
        CustomerBalancePaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the Bank transfer payment method options to pass to invoices created by the subscription."
        ),
    ] = None
    konbini: Annotated[
        KonbiniPaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the Konbini payment method options to pass to invoices created by the subscription."
        ),
    ] = None
    payto: Annotated[
        PaytoPaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the PayTo payment method options to pass to invoices created by the subscription."
        ),
    ] = None
    sepa_debit: Annotated[
        SepaDebitPaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the SEPA Direct Debit payment method options to pass to invoices created by the subscription."
        ),
    ] = None
    us_bank_account: Annotated[
        UsBankAccountPaymentMethodOptions | None,
        Field(
            description="This sub-hash contains details about the ACH direct debit payment method options to pass to invoices created by the subscription."
        ),
    ] = None


class PaymentSettings(BaseModel):
    """Payment settings passed on to invoices created by the subscription."""

    payment_method_options: Annotated[
        PaymentMethodOptions | None,
        Field(
            description="Payment-method-specific configuration to provide to invoices created by the subscription."
        ),
    ] = None
    payment_method_types: Annotated[
        list[
            Literal[
                "ach_debit",
                "acss_debit",
                "affirm",
                "amazon_pay",
                "au_becs_debit",
                "bacs_debit",
                "bancontact",
                "boleto",
                "card",
                "cashapp",
                "crypto",
                "custom",
                "customer_balance",
                "eps",
                "fpx",
                "giropay",
                "grabpay",
                "ideal",
                "kakao_pay",
                "klarna",
                "konbini",
                "kr_card",
                "link",
                "multibanco",
                "naver_pay",
                "nz_bank_account",
                "p24",
                "pay_by_bank",
                "payco",
                "paynow",
                "paypal",
                "payto",
                "promptpay",
                "revolut_pay",
                "sepa_debit",
                "sofort",
                "us_bank_account",
                "wechat_pay",
            ]
        ]
        | None,
        Field(
            description="The list of payment method types to provide to every invoice created by the subscription. If not set, Stripe attempts to automatically determine the types to use by looking at the invoice's default payment method, the subscription's default payment method, the customer's default payment method, and your invoice template settings."
        ),
    ] = None
    save_default_payment_method: Annotated[
        Literal["off", "on_subscription"] | None,
        Field(
            description="Configure whether Stripe updates `subscription.default_payment_method` when payment succeeds. Defaults to `off`."
        ),
    ] = None


class PendingInvoiceItemInterval(BaseModel):
    """Specifies an interval for how often to bill for any pending invoice items."""

    interval: Annotated[
        Literal["day", "week", "month", "year"],
        Field(
            description="Specifies invoicing frequency. Either `day`, `week`, `month` or `year`."
        ),
    ]
    interval_count: Annotated[
        int,
        Field(
            description="The number of intervals between invoices. For example, `interval=month` and `interval_count=3` bills every 3 months. Maximum of one year interval allowed (1 year, 12 months, or 52 weeks)."
        ),
    ]


class PendingUpdate(BaseModel):
    """If specified, pending updates that will be applied to the subscription once the `latest_invoice` has been paid."""

    billing_cycle_anchor: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="If the update is applied, determines the date of the first full invoice, and, for plans with `month` or `year` intervals, the day of the month for subsequent invoices. The timestamp is in UTC format."
        ),
    ] = None
    expires_at: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="The point after which the changes reflected by this update will be discarded and no longer applied."
        ),
    ]
    subscription_items: Annotated[
        list[SubscriptionItem] | None,
        Field(
            description="List of subscription items, each with an attached plan, that will be set if the update is applied."
        ),
    ] = None
    trial_end: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Unix timestamp representing the end of the trial period the customer will get before being charged for the first time, if the update is applied."
        ),
    ] = None
    trial_from_plan: Annotated[
        bool | None,
        Field(
            description="Indicates if a plan's `trial_period_days` should be applied to the subscription. Setting `trial_end` per subscription is preferred, and this defaults to `false`. Setting this flag to `true` together with `trial_end` is not allowed."
        ),
    ] = None


class TransferDataSubscription(BaseModel):
    """The account (if any) the subscription's payments will be attributed to for tax reporting, and where funds from each payment will be transferred to for each of the subscription's invoices."""

    amount_percent: Annotated[
        float | None,
        Field(
            description="A non-negative decimal between 0 and 100, with at most two decimal places. This represents the percentage of the subscription invoice total that will be transferred to the destination account. By default, the entire amount is transferred to the destination."
        ),
    ] = None
    destination: Annotated[
        str,
        Field(
            description="The account where funds from the payment will be transferred to upon payment success."
        ),
    ]


class Subscription(BaseModel):
    """Complete Stripe Subscription object."""

    # Core identifiers and metadata
    id: Annotated[str, Field(description="Unique identifier for the object.")]
    object: Annotated[
        Literal["subscription"],
        Field(
            description="String representing the object's type. Always 'subscription'."
        ),
    ] = "subscription"
    livemode: Annotated[
        bool,
        Field(
            description="Has the value `true` if the object exists in live mode or the value `false` if the object exists in test mode."
        ),
    ]

    # Application and fees
    application: Annotated[
        str | None,
        Field(
            description="ID of the Connect Application that created the subscription."
        ),
    ] = None
    application_fee_percent: Annotated[
        float | None,
        Field(
            description="A non-negative decimal between 0 and 100, with at most two decimal places. This represents the percentage of the subscription invoice total that will be transferred to the application owner's Stripe account."
        ),
    ] = None

    # Automatic tax
    automatic_tax: Annotated[
        SubscriptionAutomaticTax,
        Field(description="Automatic tax settings for this subscription."),
    ]

    # Billing cycle
    billing_cycle_anchor: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="The reference point that aligns future billing cycle dates. It sets the day of week for `week` intervals, the day of month for `month` and `year` intervals, and the month of year for `year` intervals. The timestamp is in UTC format."
        ),
    ]
    billing_cycle_anchor_config: Annotated[
        BillingCycleAnchorConfig | None,
        Field(
            description="The fixed values used to calculate the `billing_cycle_anchor`."
        ),
    ] = None
    billing_mode: Annotated[
        SubscriptionBillingMode,
        Field(
            description="Controls how prorations and invoices for subscriptions are calculated and orchestrated."
        ),
    ]
    billing_thresholds: Annotated[
        BillingThresholds | None,
        Field(
            description="Define thresholds at which an invoice will be sent, and the subscription advanced to a new billing period"
        ),
    ] = None

    # Cancellation
    cancel_at: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="A date in the future at which the subscription will automatically get canceled"
        ),
    ] = None
    cancel_at_period_end: Annotated[
        bool,
        Field(
            description="Whether this subscription will (if `status=active`) or did (if `status=canceled`) cancel at the end of the current billing period."
        ),
    ]
    canceled_at: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="If the subscription has been canceled, the date of that cancellation. If the subscription was canceled with `cancel_at_period_end`, `canceled_at` will reflect the time of the most recent update request, not the end of the subscription period when the subscription is automatically moved to a canceled state."
        ),
    ] = None
    cancellation_details: Annotated[
        CancellationDetails | None,
        Field(description="Details about why this subscription was cancelled"),
    ] = None

    # Collection method
    collection_method: Annotated[
        Literal["charge_automatically", "send_invoice"],
        Field(
            description="Either `charge_automatically`, or `send_invoice`. When charging automatically, Stripe will attempt to pay this subscription at the end of the cycle using the default source attached to the customer. When sending an invoice, Stripe will email your customer an invoice with payment instructions and mark the subscription as `active`."
        ),
    ]

    # Timestamps
    created: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Time at which the object was created. Measured in seconds since the Unix epoch."
        ),
    ]

    # Currency and customer
    currency: Annotated[
        str,
        Field(
            description="Three-letter ISO currency code, in lowercase. Must be a supported currency."
        ),
    ]
    customer: Annotated[
        str,
        Field(description="ID of the customer who owns the subscription."),
    ]
    customer_account: Annotated[
        str | None,
        Field(description="ID of the account who owns the subscription."),
    ] = None

    # Payment days and methods
    days_until_due: Annotated[
        int | None,
        Field(
            description="Number of days a customer has to pay invoices generated by this subscription. This value will be `null` for subscriptions where `collection_method=charge_automatically`."
        ),
    ] = None
    default_payment_method: Annotated[
        str | None,
        Field(
            description="ID of the default payment method for the subscription. It must belong to the customer associated with the subscription."
        ),
    ] = None
    default_source: Annotated[
        str | None,
        Field(
            description="ID of the default payment source for the subscription. It must belong to the customer associated with the subscription and be in a chargeable state."
        ),
    ] = None
    default_tax_rates: Annotated[
        list[TaxRate] | None,
        Field(
            description="The tax rates that will apply to any subscription item that does not have `tax_rates` set. Invoices created will have their `default_tax_rates` populated from the subscription."
        ),
    ] = None

    # Description and discounts
    description: Annotated[
        str | None,
        Field(
            description="The subscription's description, meant to be displayable to the customer. Use this field to optionally store an explanation of the subscription for rendering in Stripe surfaces and certain local payment methods UIs. The maximum length is 500 characters."
        ),
    ] = None
    discounts: Annotated[
        list[str],
        Field(
            description="The discounts applied to the subscription. Subscription item discounts are applied before subscription discounts. Use `expand[]=discounts` to expand each discount."
        ),
    ] = []

    # End date
    ended_at: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="If the subscription has ended, the date the subscription ended."
        ),
    ] = None

    # Invoice settings
    invoice_settings: Annotated[
        SubscriptionInvoiceSettings,
        Field(description="All invoices will be billed using the specified settings."),
    ]

    # Items
    items: Annotated[
        SubscriptionItems,
        Field(description="List of subscription items, each with an attached price."),
    ]

    # Latest invoice
    latest_invoice: Annotated[
        str | None,
        Field(description="The most recent invoice this subscription has generated."),
    ] = None

    # Metadata
    metadata: Annotated[
        dict[str, Any],
        Field(
            description="Set of key-value pairs that you can attach to an object. This can be useful for storing additional information about the object in a structured format."
        ),
    ] = {}

    # Next pending invoice
    next_pending_invoice_item_invoice: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Specifies the approximate timestamp on which any pending invoice items will be billed according to the schedule provided at `pending_invoice_item_interval`."
        ),
    ] = None

    # On behalf of
    on_behalf_of: Annotated[
        str | None,
        Field(
            description="The account (if any) the charge was made on behalf of for charges associated with this subscription."
        ),
    ] = None

    # Pause collection
    pause_collection: Annotated[
        PauseCollection | None,
        Field(
            description="If specified, payment collection for this subscription will be paused. Note that the subscription status will be unchanged and will not be updated to `paused`. Learn more about pausing collection."
        ),
    ] = None

    # Payment settings
    payment_settings: Annotated[
        PaymentSettings | None,
        Field(
            description="Payment settings passed on to invoices created by the subscription."
        ),
    ] = None

    # Pending invoice item interval
    pending_invoice_item_interval: Annotated[
        PendingInvoiceItemInterval | None,
        Field(
            description="Specifies an interval for how often to bill for any pending invoice items. It is analogous to calling Create an invoice for the given subscription at the specified interval."
        ),
    ] = None

    # Pending setup intent
    pending_setup_intent: Annotated[
        str | None,
        Field(
            description="You can use this SetupIntent to collect user authentication when creating a subscription without immediate payment or updating a subscription's payment method, allowing you to optimize for off-session payments."
        ),
    ] = None

    # Pending update
    pending_update: Annotated[
        PendingUpdate | None,
        Field(
            description="If specified, pending updates that will be applied to the subscription once the `latest_invoice` has been paid."
        ),
    ] = None

    # Schedule
    schedule: Annotated[
        str | None,
        Field(description="The schedule attached to the subscription"),
    ] = None

    # Start date
    start_date: Annotated[
        datetime,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="Date when the subscription was first created. The date might differ from the `created` date due to backdating."
        ),
    ]

    # Status
    status: Annotated[
        Literal[
            "incomplete",
            "incomplete_expired",
            "trialing",
            "active",
            "past_due",
            "canceled",
            "unpaid",
            "paused",
        ],
        Field(
            description="Possible values are `incomplete`, `incomplete_expired`, `trialing`, `active`, `past_due`, `canceled`, `unpaid`, or `paused`."
        ),
    ]

    # Test clock
    test_clock: Annotated[
        str | None,
        Field(description="ID of the test clock this subscription belongs to."),
    ] = None

    # Transfer data
    transfer_data: Annotated[
        TransferDataSubscription | None,
        Field(
            description="The account (if any) the subscription's payments will be attributed to for tax reporting, and where funds from each payment will be transferred to for each of the subscription's invoices."
        ),
    ] = None

    # Trial
    trial_end: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(description="If the subscription has a trial, the end of that trial."),
    ] = None
    trial_settings: Annotated[
        TrialSettings | None,
        Field(description="Settings related to subscription trials."),
    ] = None
    trial_start: Annotated[
        datetime | None,
        BeforeValidator(coerce_timestamp_to_datetime),
        Field(
            description="If the subscription has a trial, the beginning of that trial."
        ),
    ] = None


class ItemBillingThresholds(BaseModel):
    """Define thresholds at which an invoice will be sent, and the subscription advanced to a new billing period"""

    usage_gte: Annotated[
        int | None,
        Field(
            description="Usage threshold that triggers the subscription to advance to a new billing period"
        ),
    ] = None


class SubscriptionItemUpdate(BaseModel):
    billing_thresholds: Annotated[
        ItemBillingThresholds | None,
        Field(
            description="Define thresholds at which an invoice will be sent, and the subscription advanced to a new billing period"
        ),
    ] = None
    clear_usage: Annotated[
        bool | None,
        Field(
            description="Delete all usage for the given subscription item. Defaults to false."
        ),
    ] = None
    discounts: Annotated[
        list[Discount] | None,
        Field(description="List of discounts to apply to this subscription item."),
    ] = None
    id: Annotated[
        str,
        Field(description="The ID of the subscription item to update."),
    ]
    metadata: Annotated[
        dict[str, Any] | None,
        Field(
            description="Set of key-value pairs that you can attach to an object. This can be useful for storing additional information about the object in a structured format."
        ),
    ] = None
    quantity: Annotated[
        int | None,
        Field(description="Quantity of the subscription item."),
    ] = None
    price: Annotated[
        str | None,
        Field(description="The ID of the price object."),
    ] = None
    price_data: Annotated[
        PriceData | None,
        Field(description="Data used to generate a new price object."),
    ] = None
    tax_rates: Annotated[
        list[str] | None,
        Field(description="ID of Tax rates applied to this subscription item."),
    ] = None
