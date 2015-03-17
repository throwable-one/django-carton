from decimal import Decimal

from django.conf import settings

from carton import module_loading
from carton import settings as carton_settings

import simplejson as sj


def _dict2key(dct):
    return tuple(sorted(dct.items()))


class CartItem(object):
    """
    A cart item, with the associated product, its quantity and its price.
    """
    def __init__(self, product, quantity, price):
        self.product = product
        self.quantity = int(quantity)
        self.price = Decimal(price)

    def __repr__(self):
        return u'CartItem Object (%s)' % self.product

    def to_dict(self):
        return {
            'quantity': self.quantity,
            'price': self.price,
        }

    @property
    def subtotal(self):
        """
        Subtotal for the cart item.
        """
        return self.price * self.quantity


class Cart(object):
    def __init__(self, session, session_key=None):
        self._items_dict = {}
        self.session = session
        self.session_key = session_key or carton_settings.CART_SESSION_KEY
        # If a cart representation was previously stored in session, then we
        # TODO: with statemant. clear the cart if something wrong
        if self.session_key in self.session:
            # rebuild the cart object from that serialized representation.
            cart_representation = sj.loads(self.session[self.session_key] or '{}')
            ids_in_cart = set(item['key']['_pk'] for item in cart_representation)
            products_queryset = self.get_queryset().filter(pk__in=ids_in_cart)
            for item in (
                x for x in cart_representation
                if x['key']['_pk'] in (i.pk for i in products_queryset)
            ):
                val = CartItem(products_queryset.get(pk=item['key']['_pk']), **item['value'])
                val.__dict__.update(item['key'])
                self._items_dict[_dict2key(item['key'])] = val

    def __contains__(self, product):
        """
        Checks if the given product is in the cart.
        """
        return product in self.products

    def get_product_model(self):
        return module_loading.get_product_model()

    def filter_products(self, queryset):
        """
        Applies lookup parameters defined in settings.
        """
        lookup_parameters = getattr(settings, 'CART_PRODUCT_LOOKUP', None)
        if lookup_parameters:
            queryset = queryset.filter(**lookup_parameters)
        return queryset

    def get_queryset(self):
        product_model = self.get_product_model()
        queryset = product_model._default_manager.all()
        queryset = self.filter_products(queryset)
        return queryset

    def update_session(self):
        """
        Serializes the cart data, saves it to session and marks session as modified.
        """
        self.session[self.session_key] = self.cart_serializable
        self.session.modified = True

    def add(self, product, price=None, quantity=1, **kargs):
        """
        Adds or creates products in cart. For an existing product,
        the quantity is increased and the price is ignored.
        """
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError('Quantity must be at least 1 when adding to cart')
        kargs['_pk'] = product.pk
        key = _dict2key(kargs)
        if key in self._items_dict:
            self._items_dict[key].quantity += quantity
        else:
            if price == None:
                raise ValueError('Missing price when adding to cart')
            self._items_dict[key] = CartItem(product, quantity, price)
        self.update_session()

    def remove(self, product, **kargs):
        """
        Removes the product.
        """
        kargs['_pk'] = product.pk
        key = _dict2key(kargs)
        if key in self._items_dict:
            del self._items_dict[key]
            self.update_session()

    def remove_single(self, product, **kargs):
        """
        Removes a single product by decreasing the quantity.
        """
        kargs['_pk'] = product.pk
        key = dict2key(kargs)
        if key in self._items_dict:
            if self._items_dict[key].quantity <= 1:
                # There's only 1 product left so we drop it
                del self._items_dict[key]
            else:
                self._items_dict[key].quantity -= 1
            self.update_session()

    def clear(self):
        """
        Removes all items.
        """
        self._items_dict = {}
        self.update_session()

    def _items_gen(self):
        for key, item in self._items_dict.items():
            # TODO avoid accidental changing one of key attributes (product_pk, quantity, price)
            yield item

    @property
    def items(self):
        """
        The list of cart items.
        """
        return [x for x in self._items_gen()]

    @property
    def cart_serializable(self):
        ret = []
        for key, value in self._items_dict.items():
            ret.append({'key': {k:v for k,v in key}, 'value': value.to_dict()})
        return sj.dumps(ret)

    #TODO Do I really need it?
    #@property
    #def items_serializable(self):

    @property
    def count(self):
        return sum(item.quantity for item in self._items_gen())

    @property
    def unique_count(self):
        """
        The number of unique items in cart, regardless of the quantity.
        """
        return len(self._items_dict)

    @property
    def is_empty(self):
        return self.unique_count == 0

    @property
    def products(self):
        return (item.product for item in self._items_gen())

    @property
    def total(self):
        return sum(item.subtotal for item in self._items_gen())
